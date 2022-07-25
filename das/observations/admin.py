import copy
import csv
import random
import urllib
from datetime import datetime, timedelta
from functools import partial
from urllib.parse import quote as urlquote
from uuid import UUID

import humanize
import pytz
from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.options import FORMFIELD_FOR_DBFIELD_DEFAULTS
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import quote
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_permission_codename
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import transaction
from django.db.models import (Aggregate, BooleanField, Count, DateTimeField,
                              ExpressionWrapper, F, Max, Min, OuterRef, Q,
                              Subquery, Window)
from django.db.models.functions import FirstValue, Now, Trunc
from django.db.utils import IntegrityError
from django.forms import BaseModelFormSet, modelformset_factory
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

import observations.forms
import observations.models as models
from core.admin import (HierarchyModelAdmin, InlineExtraDynamicMixin,
                        SaveCoordinatesToCookieMixin)
from core.common import TIMEZONE_USED
from core.openlayers import OSMGeoExtendedAdmin
from observations.daterange_filter import DateRangeFilter
from observations.forms import (GPXFileForm, MessagesForm, SourceProviderForm,
                                SubjectChangeListForm, SubjectSourceForm)
from observations.tasks import (maintain_subjectstatus_for_subject,
                                process_gpxtrack_file)
from observations.utils import assigned_range_dates, get_cyclic_subjectgroup
from observations.widgets import MessageGenericForeignKeyRawIdWidget
from tracking.models import SourcePlugin
from utils.drf import TimeLimitedPaginator
from utils.html import make_html_list

from .models import SOURCE_TYPES

site_title = _('EarthRanger Administration (advanced view)')
admin.site.site_title = site_title
admin.site.site_header = site_title
admin.site.index_title = site_title

admin.site.index_template = 'admin/standard_admin_index.html'

OBSERVATIONS_HISTORY_LIMIT = timedelta(days=90)


class _RelatedFieldWidgetWrapper(admin.widgets.RelatedFieldWidgetWrapper):
    template_name = 'admin/widgets/related_widget.html'

    def __init__(self, widget,
                 rel, admin_site, can_add_related=None,
                 can_change_related=False, can_delete_related=False,
                 can_view_related=False, query_value=None):
        self.query_value = query_value
        super(_RelatedFieldWidgetWrapper, self).__init__(widget, rel, admin_site, can_add_related,
                                                         can_change_related, can_delete_related, can_view_related)

    @property
    def get_model_name(self):
        return self.rel.model.__name__

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if self.get_model_name == 'GPXTrackFile':
            context['gpx_file'] = True
            context['query_id'] = self.query_value
        return context


admin.widgets.RelatedFieldWidgetWrapper = _RelatedFieldWidgetWrapper


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(
            meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = writer.writerow([getattr(obj, field)
                                   for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected Items"


class ValidateFilterMixin:
    def difference_in_date(self, first_date, second_date):
        try:
            d1_obj = datetime.strptime(first_date, '%d/%m/%Y')
            d2_obj = datetime.strptime(second_date, '%d/%m/%Y')
        except ValueError:
            return 90
        diff_date = d2_obj - d1_obj
        return diff_date.days

    def check_uuid(self, uuid):
        try:
            UUID(uuid).version
        except Exception:
            return
        return uuid

    def parse_encoded_url(self, query_string):
        parsed_qs = urllib.parse.parse_qs(query_string)
        return parsed_qs


class SubjectSubTypeInline(InlineExtraDynamicMixin, admin.TabularInline):
    model = models.SubjectSubType

    verbose_name = _('Subject Sub-Type')
    verbose_name_plural = _('Subject Sub-Types')
    show_change_link = False

    readonly_fields = ('value',)

    fields = ('value', 'display', )

    ordering = ('display',)


@admin.register(models.SubjectType)
class SubjectTypeAdmin(admin.ModelAdmin):
    list_display = ('value', 'display',)
    list_editable = ('display', )
    readonly_fields = ('id',)
    search_fields = ('value', 'display')
    ordering = list_display

    fieldsets = (
        (None,
         {'fields': (('display', 'value')),
          'classes': ('wide',)}
         ),
    )

    inlines = [SubjectSubTypeInline, ]


@admin.register(models.SubjectSubType)
class SubjectSubTypeAdmin(admin.ModelAdmin):
    list_display = ('value', 'display', 'subject_type', )
    list_editable = ('display', 'subject_type',)
    list_filter = ('subject_type__display',)
    readonly_fields = ('id',)
    search_fields = ('value', 'display',
                     'subject_type__display', 'subject_type__value')

    ordering = ('value', 'subject_type', 'display')
    list_display_links = ('value',)

    fieldsets = (
        (None,
         {'fields': (('display', 'value', 'subject_type'))}
         ),
    )


class SubjectSourceInline(InlineExtraDynamicMixin, OSMGeoExtendedAdmin, admin.StackedInline):
    can_delete = True
    fk_name = "subject"
    form = SubjectSourceForm
    fieldsets = (
        (
            None,
            {
                "fields": (
                    (
                        "subject",
                        "source",
                    ),
                )
            },
        ),
        (None, {"classes": ("wide",), "fields": ("assigned_range",)}),
        (None, {"fields": ("location",)}),
        (
            "Source Assignment Attributes",
            {
                "classes": (
                    "wide",
                    "collapse",
                ),
                "fields": (
                    "chronofile",
                    "data_status",
                    "data_starts_source",
                    "data_stops_source",
                    "data_stops_reason",
                    "date_off_or_removed",
                    "comments",
                ),
            },
        ),
        (
            "Raw Attributes Data",
            {
                "classes": (
                    "wide",
                    "collapse",
                ),
                "fields": ("additional", "id"),
            },
        ),
    )
    model = models.SubjectSource
    readonly_fields = ("additional",)
    show_change_link = True
    template = "admin/observations/subjectsource/edit_inline/stacked.html"
    verbose_name = _("Source Assignment")
    verbose_name_plural = _("Source Assignments")

    def __init__(self, parent_model, admin_site):
        self.admin_site = admin_site
        self.parent_model = parent_model
        self.opts = self.model._meta
        self.has_registered_model = admin_site.is_registered(self.model)
        overrides = copy.deepcopy(FORMFIELD_FOR_DBFIELD_DEFAULTS)
        for k, v in self.formfield_overrides.items():
            overrides.setdefault(k, {}).update(v)
        self.formfield_overrides = overrides
        if self.verbose_name is None:
            self.verbose_name = self.model._meta.verbose_name
        if self.verbose_name_plural is None:
            self.verbose_name_plural = self.model._meta.verbose_name_plural

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-assigned_range__startswith")


class SourceGenericInline(GenericTabularInline):
    model = models.Source


class GroupAssignedFilter(admin.SimpleListFilter):
    title = 'In Group(s)?'
    parameter_name = 'is_assigned_to_groups'

    def lookups(self, request, model_admin):
        return (
            ('ingroups', 'In Groups'),
            ('nogroups', 'Not in any Groups'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'ingroups':
            return queryset.annotate(groups_count=Count('groups')).filter(groups_count__gt=0)
        elif value == 'nogroups':
            return queryset.annotate(groups_count=Count('groups')).filter(groups_count=0)
        return queryset


class InputFilter(admin.SimpleListFilter):
    '''
    Create a filter with no choices, just a simple text box.
    '''
    template = 'admin/input_filter.html'

    def lookups(self, request, model_admin):
        return ((),)

    def choices(self, changelist):

        all_choice = next(super().choices(changelist))
        all_choice['query_parts'] = (
            (k, v)
            for k, v in changelist.get_filters_params().items()
            if k != self.parameter_name
        )
        yield all_choice


class SubjectNameFilter(InputFilter):
    parameter_name = 'subject_name'
    title = _('Subject Name')

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(
                source__subjectsource__subject__name__icontains=self.value(),
                source__subjectsource__assigned_range__contains=F(
                    'recorded_at')
            )


class SubjectIdFilter(InputFilter, ValidateFilterMixin):
    parameter_name = 'subject_id'
    title = _('Subject ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            uuid = self.check_uuid(self.value())
            return queryset.filter(
                source__subjectsource__subject_id=uuid, source__subjectsource__assigned_range__contains=F(
                    'recorded_at')
            )


class SourceIdFilter(InputFilter, ValidateFilterMixin):
    parameter_name = 'source_id'
    title = _('Source ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            uuid = self.check_uuid(self.value())
            return queryset.filter(source__id=uuid)


@admin.register(models.Observation)
class ObservationAdmin(ExportCsvMixin, ValidateFilterMixin, OSMGeoExtendedAdmin):
    readonly_fields = ("created_at", "id")
    fields = ("id", "recorded_at", "created_at",
              "location", "exclusion_flags", "source", "additional")
    list_display = ('subject_link', '_manufacturer_id', '_recorded_at', '_created_at',
                    '_latitude', '_longitude', '_state', '_event_action', 'exclusion_flags')
    ordering = ('source', 'location', 'recorded_at', 'created_at', 'source')
    list_editable = ('exclusion_flags',)
    list_display_links = ('_recorded_at',)
    show_full_result_count = False
    autocomplete_fields = ('source',)

    paginator = TimeLimitedPaginator
    formfield_overrides = {
        BitField: {
            'widget': BitFieldCheckboxSelectMultiple
        },
    }

    gis_geometry_field_name = 'location'

    list_filter = (SubjectNameFilter, SubjectIdFilter,
                   SourceIdFilter, ('recorded_at', DateRangeFilter))

    def subject_link(self, obj):
        return mark_safe('<a href="{}">{}</a>'.format(
            reverse("admin:observations_subject_change",
                    args=(obj.subject_id,)),
            obj.subject_name
        ))
    subject_link.short_description = 'Subject'
    subject_link.admin_order_field = 'subject_name'

    def _longitude(self, o):
        return round(o.location.x, 5)
    _longitude.short_description = _('Longitude')

    def _latitude(self, o):
        return round(o.location.y, 5)
    _latitude.short_description = _('Latitude')

    def _state(self, o):
        return o.additional.get('radio_state') if o.additional else None
    _state.short_description = 'Radio Status'

    def _event_action(self, o):
        return o.additional.get('event_action') if o.additional else None
    _event_action.short_description = 'Event Action'

    def _subject_name(self, o):
        return o.subject_name

    def _manufacturer_id(self, o):
        return o.manufacturer_id
    _manufacturer_id.admin_order_field = 'manufacturer_id'

    def _created_at(self, o):
        return o.created_at
    _created_at.short_description = 'row created at %s' % TIMEZONE_USED
    _created_at.admin_order_field = 'created_at'

    def _recorded_at(self, o):
        return o.recorded_at
    _recorded_at.short_description = 'recorded at %s' % TIMEZONE_USED
    _recorded_at.admin_order_field = 'recorded_at'
    _recorded_at.admin_order_first_type = "desc"

    def get_queryset(self, request):
        qs = super(ObservationAdmin, self).get_queryset(request)

        if self.is_change_view(request):
            return qs

        # Reference Subject to get Name.
        # TODO: Consider a raw query.
        subject = models.Subject.objects.filter(subjectsource__source_id=OuterRef('source_id'),
                                                subjectsource__assigned_range__contains=OuterRef('recorded_at'))
        qs = qs.annotate(subject_name=Subquery(subject.values('name')[:1]))
        qs = qs.annotate(subject_id=Subquery(subject.values('id')[:1]))

        qs = qs.annotate(manufacturer_id=F('source__manufacturer_id'),
                         )
        qs = qs.select_related('source',)

        return qs

    def is_change_view(self, request):
        return "change" in request.path

    def is_date_range_set(self, request):
        query_string = request.META['QUERY_STRING']
        filter_params = self.parse_encoded_url(query_string)
        if filter_params:
            d1 = filter_params.get('recorded_at__range__gte')
            d2 = filter_params.get('recorded_at__range__lte')
            return (d1, d2) if d1 and d2 else False
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        daterange_set = self.is_date_range_set(request)
        if daterange_set:
            d1, d2 = daterange_set
            extra_context['history_limit_days'] = self.difference_in_date(
                d1[0], d2[0])
            return super().changelist_view(request, extra_context=extra_context)
        extra_context['history_limit_days'] = OBSERVATIONS_HISTORY_LIMIT.days
        return super().changelist_view(request, extra_context=extra_context)

    actions = ['export_as_csv', ]


class SourceProviderFilter(admin.SimpleListFilter, SaveCoordinatesToCookieMixin):
    title = 'Source Provider'
    parameter_name = 'provider_key'
    gis_geometry_field_name = 'location'

    def lookups(self, request, model_admin):
        return [(p.provider_key, p.display_name) for p in sorted(models.SourceProvider.objects.all(),
                                                                 key=lambda p: p.display_name.lower())]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(subjectsource__source__provider__provider_key=value)
        return queryset


class SSSourceProviderFilter(SourceProviderFilter):
    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(subject__subjectsource__source__provider__provider_key=value)
        return queryset


class SourceSourceProviderFilter(SourceProviderFilter):
    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(provider__provider_key=value)
        return queryset


class ObservationsContextMixin:
    def get_observations_context(self, extra_context, observations, id):
        """ Update extra context for rendering observations """
        model_name = self.model._meta.model_name
        extra_context = extra_context or {}
        extra_context['observations'] = observations[:25]
        extra_context['timezone'] = TIMEZONE_USED
        extra_context['filter_params'] = f"?{str(model_name)}_id={str(id)}"

        extra_context['model'] = model_name
        return extra_context


@admin.register(models.Subject)
class SubjectAdmin(ExportCsvMixin, ObservationsContextMixin, admin.ModelAdmin):
    list_display = ('name', 'subject_subtype',  # '_subject_subtype_display',
                    '_is_active', 'get_attributes', 'all_groups', 'all_sources', '_status',
                    )

    search_fields = ('name', 'subject_subtype__display', 'common_name__display',
                     'subjectsource__source__manufacturer_id')

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('id', 'name', 'subject_subtype', 'is_active', 'common_name',
                        'groups',))
        }
        ),
        ('Subject Attributes', {
            'classes': ('wide',),
            'fields': (('rgb', 'sex'))
        }
        ),
        ('ER Mobile App', {
            'classes': ('wide', 'collapse'),
            'fields': ('tm_animal_id', 'region', 'country',)
        }),
        ('Advanced Subject Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional', 'created_at', 'updated_at',)
        }),
        ('GPX Data imports', {
            'classes': ('gpx-cls',),
            'fields': ('import_gpx_data',)
        })
    )
    list_filter = ('is_active', GroupAssignedFilter,
                   'subject_subtype__subject_type__display',
                   'subject_subtype__display',
                   SourceProviderFilter
                   )
    list_editable = ('subject_subtype',)
    readonly_fields = ('id', 'created_at', 'updated_at',)
    list_per_page = 25
    ordering = ('name',)

    def get_fieldsets(self, request, obj=None):
        """
        Hook for specifying fieldsets.
        """
        subject_region_enabled = getattr(
            settings, 'SUBJECT_REGION_ENABLED', False)

        if subject_region_enabled:
            return super().get_fieldsets(request, obj=None)
        else:
            if self.fieldsets:
                fieldsets = list(self.fieldsets)
                for item in fieldsets:
                    if 'ER Mobile App' in item:
                        fieldsets.pop(fieldsets.index(item))
                return tuple(fieldsets)
            return [(None, {'fields': self.get_fields(request, obj)})]

    def _status(self, o):

        return mark_safe(f'<img src="{o.image_url}" style="height:2.0em;"/>')
    _status.short_description = _('Map Marker')

    def _is_active(self, o):
        return o.is_active

    _is_active.short_description = _('Active?')
    _is_active.boolean = True

    def assign_random_color(self, request, queryset):
        update_count = 0
        for item in queryset:
            if hasattr(item, 'additional') and not item.additional.get('rgb'):
                item.additional['rgb'] = ','.join(
                    [str(random.randint(0, 255)) for i in range(3)])
                item.save()
                update_count += 1

        if update_count == 1:
            msg = 'One subject was updated with a random color.'
        else:
            msg = '%s subjects were updated each with a random color.' % (
                update_count,)

        self.message_user(request, msg)

    assign_random_color.short_description = _('Assign random color')

    actions = ['assign_random_color', 'export_as_csv', ]

    inlines = [SubjectSourceInline, ]

    def get_queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectAdmin, self).get_queryset(request)
        qs = qs.annotate(groups_names=ArrayAgg('groups__name', distinct=True, ordering=F('groups__name')))\
            .prefetch_related('subject_subtype', 'subjectsources',)
        return qs

    def _subject_subtype_display(self, o):
        return o.subject_subtype.display

    _subject_subtype_display.short_description = 'Subject Sub-Type'

    def annotate_with_latest_observation(self, queryset):
        '''
        Annotate Subject record with latest Observation.
        This should be not be done by default.
        :param queryset:
        :return: updated queryset
        '''
        newest = models.Observation.objects.filter(
            source__subjectsource__subject=OuterRef('pk'),
            source__subjectsource__assigned_range__contains=F('recorded_at')).exclude(
            location=models.EMPTY_POINT).order_by('-recorded_at')
        return queryset.annotate(newest_observation_at=Subquery(newest.values('recorded_at')[:1]))

    form = observations.forms.SubjectForm
    save_on_top = True

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == 'common_name':
            kwargs['queryset'] = models.CommonName.objects.all()

        if db_field.name == 'subject_subtype':
            kwargs['queryset'] = models.SubjectSubType.objects.order_by(
                'display')

        return super().formfield_for_foreignkey(db_field, request=request, **kwargs)

    def get_attributes(self, instance):
        context = dict((k, instance.additional[k]) for k in (
            'rgb', 'region', 'country', 'sex', 'age') if k in instance.additional)

        return mark_safe(''.join('<p><strong>{}</strong>: {}</p>'.format(escape(k), escape(v))
                                 for k, v in context.items()))

    get_attributes.short_description = _('Subject Attributes')

    def all_groups(self, instance):

        gnlist = [x for x in instance.groups_names if x is not None]
        if gnlist:
            return make_html_list(gnlist)
        else:
            return ''

    all_groups.short_description = _('Groups')
    all_groups.allow_tags = True

    def all_sources(self, instance):
        '''
        Get all the source assignments for this Subject and annotate each assignment to indicate whether it is
        'current' meaning that its assignment range includes 'now'.
        :param instance:
        :return:
        '''
        subjectsources = models.SubjectSource \
            .objects \
            .filter(subject_id=instance.pk).annotate(manufacturer_id=F('source__manufacturer_id'), provider_display=F('source__provider__display_name')) \
            .annotate(current=ExpressionWrapper(Q(assigned_range__contains=Now()), output_field=BooleanField())) \
            .order_by('-assigned_range__startswith')

        def set_current_flag(o):
            if o['current']:
                o['active_icon'] = settings.STATIC_URL + 'admin/img/icon-yes.svg'
            else:
                o['active_icon'] = settings.STATIC_URL + 'admin/img/icon-no.svg'
            return o

        subjectsources = list(set_current_flag(o)
                              for o in subjectsources.values())

        content = render_to_string(
            'admin/subjectsource.html', {'subjectsources': list(subjectsources), 'timezone': TIMEZONE_USED})

        return format_html(content)

    all_sources.short_description = _('Source Assignments')
    all_sources.allow_tags = True

    def get_changelist_form(self, request, **kwargs):
        return SubjectChangeListForm

    @staticmethod
    def get_gpxdata_context(extra_context, gpxdata, object_id):
        extra_context = extra_context or {}
        _url = reverse('admin:observations_gpxtrackfile_changelist')
        filter_param = 'source_assignment__subject__id__exact'
        extra_context['gpxdata'] = gpxdata[:3]
        extra_context['query_filter'] = f'{_url}?{filter_param}={object_id}' if gpxdata.count(
        ) > 3 else None
        return extra_context

    def check_for_no_trackpoints_import_failure(self, request, gpx_uploads):
        no_trackpoint_records = gpx_uploads.filter(
            created_by=request.user, status_description__isnull=False)

        if no_trackpoint_records:
            message = no_trackpoint_records.first().get('status_description')
            messages.add_message(request, messages.WARNING, message)
            no_trackpoint_records.update(status_description=None)

    def change_view(self, request, object_id, form_url='', extra_context=None):

        latest_observations = models.Observation.objects.filter(
            source__subjectsource__subject__id=object_id,
            source__subjectsource__assigned_range__contains=F('recorded_at')).order_by('-recorded_at')\
            .values('source__manufacturer_id', 'recorded_at', 'location', 'additional')
        extra_context = self.get_observations_context(
            extra_context, latest_observations, object_id)

        if request.user.has_any_perms(('observations.add_observation'
                                       'observations.view_observation',
                                       'observations.change_observation')):
            latest_gpx_upload = models.GPXTrackFile.objects.filter(source_assignment__subject=object_id). \
                annotate(subject_name=F('source_assignment__subject__name'),
                         source_name=F(
                             'source_assignment__source__manufacturer_id'),
                         username=F('created_by__username')).order_by('-processed_date').values()
            extra_context = self.get_gpxdata_context(
                extra_context, latest_gpx_upload, object_id)

        self.check_for_no_trackpoints_import_failure(
            request, latest_gpx_upload)

        return super().change_view(
            request, object_id, form_url, extra_context=extra_context,
        )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        none_qs = models.GPXTrackFile.objects.none()
        form.base_fields['import_gpx_data'].queryset = none_qs
        return form

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'import_gpx_data':
            formfield = self.formfield_for_foreignkey(
                db_field, request, **kwargs)
            related_modeladmin = self.admin_site._registry.get(
                db_field.remote_field.model)
            wrapper_kwargs = {}
            if related_modeladmin:
                wrapper_kwargs.update(
                    can_add_related=related_modeladmin.has_add_permission(
                        request),
                    can_change_related=related_modeladmin.has_change_permission(
                        request),
                    can_delete_related=related_modeladmin.has_delete_permission(
                        request),
                    can_view_related=related_modeladmin.has_view_permission(
                        request),
                    query_value=request.resolver_match.kwargs.get('object_id'),
                )
            formfield.widget = _RelatedFieldWidgetWrapper(
                formfield.widget, db_field.remote_field, self.admin_site, **wrapper_kwargs
            )
            return formfield
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def _changeform_view(self, request, object_id, form_url, extra_context):
        if request.GET and request.GET.get('popup') == 'false' and \
                not request.user.has_perm('observations.add_observation'):
            error_msg = "Error: User does not have permissions to create Observation records"
            self.message_user(request, error_msg, level=messages.ERROR)
        return super(SubjectAdmin, self)._changeform_view(request, object_id, form_url, extra_context)


@admin.register(models.CommonName)
class CommonNameAdmin(admin.ModelAdmin):
    list_display = ('value', 'display', 'subject_subtype')
    ordering = list_display

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(CommonNameAdmin, self).queryset(request)
        if request.user.is_superuser:
            return qs

        raise NotImplementedError(
            'implement filtering SubjectAdmin to user permissions')
        return qs.filter(owner=request.user)


@admin.register(models.GPXTrackFile)
class GPXAdmin(admin.ModelAdmin, ValidateFilterMixin):
    readonly_fields = ('id',)
    list_display = ('subject', 'source', 'filename', '_file_size', 'description', 'processed_date',
                    'processed_status', '_points_imported', 'created_by', 'id')
    list_filter = ('source_assignment__subject', )
    fields = ('id', 'source_assignment', 'description', 'data')
    ordering = ('-processed_date',)
    list_display_links = None
    observation_opts = models.Observation._meta
    form = GPXFileForm

    def get_model_perms(self, request):
        # Hides this page from showing up on admin site.
        return {}

    def has_add_permission(self, request):
        opts = self.observation_opts
        codename = get_permission_codename('add', opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    def has_change_permission(self, request, obj=None):
        opts = self.observation_opts
        codename = get_permission_codename('change', opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    def has_delete_permission(self, request, obj=None):
        opts = self.observation_opts
        codename = get_permission_codename('delete', opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    def has_view_permission(self, request, obj=None):
        opts = self.observation_opts
        codename_view = get_permission_codename('view', opts)
        codename_add = get_permission_codename('add', opts)
        codename_change = get_permission_codename('change', opts)
        return (
            request.user.has_perm(f"{opts.app_label}.{codename_view}") or
            request.user.has_perm(f"{opts.app_label}.{codename_add}") or
            request.user.has_perm(f"{opts.app_label}.{codename_change}"))

    def get_form(self, request, obj=None, change=False, **kwargs):
        """
        :param request:
        :param obj:
        :param change:
        :param kwargs:
        :return: form
        """
        form = super(GPXAdmin, self).get_form(request, obj, change, **kwargs)
        if not change:
            subject_id = request.GET.get('subject_id')
            none_qs = models.SubjectSource.objects.none()
            queryset = models.Subject.objects.get(
                id=subject_id).subjectsources.all() if self.check_uuid(subject_id) else none_qs
            form.base_fields['source_assignment'].widget = forms.Select()
            form.base_fields['source_assignment'].queryset = queryset
            form.base_fields['source_assignment'].initial = queryset.last()
        else:
            form.base_fields['source_assignment'].widget = forms.Select()
        return form

    def response_add(self, request, obj, post_url_continue=None):
        """
        Determine the HttpResponse for the add_view stage.
        """
        opts = obj._meta
        preserved_filters = self.get_preserved_filters(request)
        obj_url = reverse(
            'admin:%s_%s_change' % (opts.app_label, opts.model_name),
            args=(quote(obj.pk),),
            current_app=self.admin_site.name,
        )
        # Add a link to the object's change form if the user can edit the obj.
        if self.has_change_permission(request, obj):
            obj_repr = format_html('<a href="{}">{}</a>',
                                   urlquote(obj_url), obj)
        else:
            obj_repr = str(obj)
        msg_dict = {'name': opts.verbose_name,
                    'obj': obj_repr, 'filename': obj.file_name}

        if "_addanother" in request.POST:

            msg = format_html(
                _('The GPX data file "{filename}" was successfully uploaded for processing. You may add another {name} below.'),
                **msg_dict
            )
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = request.get_full_path()
            redirect_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)
        else:

            msg = format_html(
                _('The GPX data file "{filename}" was successfully uploaded for processing.',),
                **msg_dict
            )
            self.message_user(request, msg, messages.SUCCESS)
            return super().response_add(request, obj, post_url_continue)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # atomic blocks can be nested. In this case,
        # when an inner block completes successfully,
        # its effects can still be rolled back if an exception is raised in the outer block at a later point.
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except Exception as exc:
            url_path = request.get_full_path()
            file_name = request.FILES.get('data').name
            error_msg = f'The GPX data file "{file_name}" failed to be processed: {exc}'
            self.message_user(request, error_msg, level=messages.ERROR)
            self.create_gpxfile_object(request)
            return HttpResponseRedirect(url_path)

    def save_model(self, request, obj, form, change):
        obj.processed_status = self.model.pending
        obj.file_size = obj.data.size
        obj.file_name = obj.data.name
        obj.created_by = request.user
        saved = obj.save()
        transaction.on_commit(lambda: process_gpxtrack_file.delay(obj.id))
        return saved

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(subject_name=F('source_assignment__subject__name'),
                                     source_name=F('source_assignment__source__manufacturer_id'))
        return queryset

    def create_gpxfile_object(self, request):
        """When gpx file upload fails, create one with status=Failure"""
        model = self.model
        posted_data = request.POST
        posted_file = request.FILES
        data = posted_file.get('data')
        file_name = data.name
        file_size = data.size
        user = request.user
        source_assignment = posted_data.get('source_assignment')
        subject_source = models.SubjectSource.objects.get(id=source_assignment)
        description = posted_data.get('description')
        return model.objects.create(source_assignment=subject_source,
                                    description=description,
                                    processed_status=self.model.failure,
                                    file_size=file_size,
                                    file_name=file_name,
                                    created_by=user)

    def source(self, o):
        return o.source_name
    source.short_description = 'Source'
    source.admin_order_field = 'source_name'

    def subject(self, o):
        return o.subject_name
    subject.short_description = 'Subject'
    subject.admin_order_field = 'subject_name'

    def filename(self, o):
        return o.file_name
    filename.short_description = 'File Name'
    filename.admin_order_field = 'file_name'

    def _file_size(self, o):
        return f'{o.file_size:,}'
    _file_size.short_description = 'File Size (Bytes)'

    def _points_imported(self, o):
        imported_points = o.points_imported
        try:
            imported_points = f'{int(imported_points):,}'
        except Exception:
            pass
        return imported_points if imported_points else '-'
    _points_imported.short_description = 'Track Points Imported'


@admin.register(models.SubjectSourceSummary)
class SubjectSourceSummaryAdmin(admin.ModelAdmin):
    list_display = ('source', '_subject', '_source_plugin',
                    '_plugin', '_provider', '_start_date', '_end_date')
    list_filter = ('source__provider__display_name',)
    search_fields = ('source__manufacturer_id', 'subject__name',
                     'source__provider__display_name')
    ordering = ('source', 'subject')

    def record_link(self, url, key, view):
        return mark_safe('<a href="{}">{}</a>'.format(
            reverse(url, args=(key,)), view
        ))

    def _subject(self, o):
        return self.record_link("admin:observations_subject_change", o.subject.id, o.subject)
    _subject.admin_order_field = 'subject'

    def _provider(self, o):
        provider = o.source.provider
        return self.record_link("admin:observations_sourceprovider_change", provider.pk, provider.display_name)

    def _source_plugin(self, o):
        source_plugin = SourcePlugin.objects.get(source=o.source)
        return self.record_link("admin:tracking_sourceplugin_change", source_plugin.id, source_plugin.plugin_type)

    def _plugin(self, o):
        source_plugin = SourcePlugin.objects.get(source=o.source)
        return source_plugin.plugin.name

    def _start_date(self, o):
        start_date, _ = assigned_range_dates(o)
        return start_date

    def _end_date(self, o):
        _, end_date = assigned_range_dates(o)
        return end_date

    def has_add_permission(self, request):
        return False

    form = SubjectSourceForm

    fieldsets = (
        (None, {
            'fields': (('subject', 'source'),)
        }
        ),
        ('Assigned Range', {
            'classes': ('wide',),
            'fields': ('assigned_range',)
        }
        ),
        ('Attributes', {
            'classes': ('wide',),
            'fields': ('chronofile', 'data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason', 'date_off_or_removed', 'comments')
        }
        ),
        ('Advanced', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional',)
        }
        )
    )


@admin.register(models.Source)
class SourceAdmin(admin.ModelAdmin, ObservationsContextMixin):
    list_display = ['manufacturer_id', 'source_type',
                    'model_name', 'get_attributes', '_source_provider', ]
    ordering = ('manufacturer_id', 'source_type', 'model_name', 'provider')
    search_fields = ('id', 'manufacturer_id', 'model_name', 'additional',)
    list_filter = ('source_type', 'model_name', SourceSourceProviderFilter)
    readonly_fields = ('id', 'created_at', 'updated_at',)
    #    filter_horizontal = ('groups',)

    form = observations.forms.SourceForm
    fieldsets = (
        (None, {
            'fields': ('manufacturer_id', 'source_type', 'model_name',
                       'provider', 'collar_key')
        }
        ),
        ('Source Attributes', {
            'classes': ('wide',),
            'fields': ('collar_status', 'collar_model', 'has_acc_data',
                       'collar_manufacturer', 'datasource', 'data_owners',
                       'adjusted_beacon_freq', 'frequency',
                       'adjusted_frequency',
                       'backup_frequency', 'predicted_expiry',
                       'feed_id', 'feed_passwd'
                       )
        }
        ),
        ('Data Source Configuration', {
            'classes': ('wide',),
            'fields': ('silence_notification_threshold', 'two_way_messaging')
        }
        ),

        ('Advanced Source Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'additional', 'created_at', 'updated_at')
        }
        )
    )

    def get_attributes(self, instance):
        context = dict((k, instance.additional[k]) for k in (
            'frequency',) if k in instance.additional)

        return mark_safe(''.join('<p><strong>{}</strong>: {}</p>'.format(escape(k), escape(v))
                                 for k, v in context.items()))

    get_attributes.short_description = _('Source Attributes')

    def get_queryset(self, request):
        qs = super(SourceAdmin, self).get_queryset(request)
        qs = qs.select_related('provider',)
        return qs

    def _source_provider(self, o):
        return o.provider.display_name
    _source_provider.admin_order_field = 'provider'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        latest_observations = models.Observation.objects.filter(
            source__id=object_id,
            source__subjectsource__assigned_range__contains=F('recorded_at')).order_by('-recorded_at')\
            .values('source__manufacturer_id', 'recorded_at', 'location', 'additional')
        extra_context = self.get_observations_context(
            extra_context, latest_observations, object_id)
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context,
        )


class CurrentAssignmentFilter(admin.SimpleListFilter):
    title = 'Assignment Status'
    parameter_name = 'is_current_assignment'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Currently assigned'),
            ('no', 'Expired (or future) assignment'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'yes':
            return queryset.filter(current=True)
        elif value == 'no':
            return queryset.filter(current=False)
        return queryset


@admin.register(models.SubjectSource)
class SubjectSourceAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'manufacturer_id',
                    'current', '_assigned_range')
    ordering = ('subject', 'source', 'assigned_range')
    list_filter = ('source__source_type', CurrentAssignmentFilter,
                   'subject__subject_subtype__subject_type__value', 'subject__subject_subtype__value')
    search_fields = ('source__manufacturer_id', 'subject__name')
    readonly_fields = ('id',)

    def subject_name(self, o):
        return o.subject.name
    subject_name.admin_order_field = 'subject'

    def manufacturer_id(self, o):
        return o.source.manufacturer_id
    manufacturer_id.admin_order_field = 'source'

    def current(self, o):
        return o.current
    current.short_description = 'Is Current?'
    current.boolean = True

    def _assigned_range(self, o):
        return assigned_range_dates(o)

    fieldsets = (
        (None, {
            'fields': (('subject', 'source'),)
        }
        ),
        ('Assigned Range', {
            'classes': ('wide',),
            'fields': ('assigned_range',)
        }
        ),
        ('Attributes', {
            'classes': ('wide',),
            'fields': ('chronofile', 'data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason', 'date_off_or_removed', 'comments')
        }
        ),
        ('Advanced', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional',)
        }
        )
    )

    form = observations.forms.SubjectSourceForm

    def get_queryset(self, request):
        qs = super(SubjectSourceAdmin, self).get_queryset(request)
        qs = qs.annotate(current=ExpressionWrapper(
            Q(assigned_range__contains=Now()), output_field=BooleanField()))

        # 'subject__subject_subtype', 'source__provider')
        qs = qs.prefetch_related('source', 'subject',)
        return qs


@admin.register(models.Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['id', 'region', 'country', 'slug']
    ordering = list_display
    fields = ['id', 'region', 'country', 'slug']
    search_fields = ('region', 'country')

    def __str__(self):
        return self.slug


class SubjectGroupChangeForm(forms.ModelForm):
    filter_horizontal = ('children', 'permission_sets', 'subjects')
    active_subjects = forms.ModelMultipleChoiceField(
        queryset=models.Subject.objects.order_by('name').by_is_active(True),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Subjects'),
            is_stacked=False
        )
    )
    inactive_subjects = forms.ModelMultipleChoiceField(
        queryset=models.Subject.objects.order_by('name').by_is_active(False),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Inactive Subjects'),
            is_stacked=False
        )
    )

    class Meta:
        model = models.SubjectGroup
        fields = ('name', 'id', 'is_visible',
                  'active_subjects', 'inactive_subjects',
                  'children', 'permission_sets')

    def __init__(self, *args, **kwargs):
        if kwargs.get('instance', None):
            instance = kwargs.get('instance')
            subjects = instance.subjects.all()
            initial = kwargs.setdefault('initial', {})
            initial['active_subjects'] = [subject.id
                                          if subject.is_active else None
                                          for subject in subjects]
            initial['inactive_subjects'] = [subject.id
                                            if not subject.is_active else None
                                            for subject in subjects]
        super().__init__(*args, **kwargs)
        self.fields[
            'children'].queryset = models.SubjectGroup.objects.exclude(
            id__exact=self.instance.id)

    def save(self, commit=True):
        instance = forms.ModelForm.save(self, False)
        instance.save()
        self.save_m2m()
        instance.subjects.clear()
        for subject in self.cleaned_data['active_subjects']:
            instance.subjects.add(subject)
        for subject in self.cleaned_data['inactive_subjects']:
            instance.subjects.add(subject)
        return instance

    def clean_children(self):
        cyclic_list = []
        groups = queryset = self.cleaned_data.get('children')
        cyclic_sg = get_cyclic_subjectgroup()

        for o in queryset:
            descendents = [q.id for q in o.get_descendants()]
            if bool(set(descendents) & set(cyclic_sg)):
                cyclic_list.append(o.name)
        if cyclic_list:
            raise forms.ValidationError(f"The following subject group {cyclic_list}  relation "
                                        f"results in cyclic dependency", code='invalid')
        return groups


class ModelFormSet(BaseModelFormSet):

    def __getitem__(self, index):
        return self.forms[index]

    @cached_property
    def forms(self):
        """Instantiate forms at first property access."""
        f = [self._construct_form(i, **self.get_form_kwargs(i))
             for i in range(self.total_form_count())]

        for index, fm in enumerate(f):
            if fm.instance.is_default and fm.has_changed():
                f[0], f[index] = fm, f[0]
        return f


class SubjectGroupException(Exception):
    pass


class DeleteDefaultSubjectGroupException(SubjectGroupException):
    pass


@admin.register(models.SubjectGroup)
class SubjectGroupAdmin(HierarchyModelAdmin):
    form = SubjectGroupChangeForm
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        (None, {'fields': ('name', 'id', 'is_visible')}),
        (None, {'fields': ('is_default',)}),
        ('Subjects', {
            'fields': ('active_subjects',)
        }),
        ('Inactive Subjects', {
            'classes': ('wide', 'collapse'),
            'fields': ('inactive_subjects',)
        }),
        ('Groups', {
            'fields': ('children',)
        }),
        (_('Permissions'), {'fields': ('permission_sets',)}),

    )
    list_display = ('name', 'is_visible', 'is_default')
    readonly_fields = ('is_default',)
    list_editable = ('is_visible', 'is_default')
    list_filter = ('is_visible',)
    filter_horizontal = ('children', 'permission_sets', 'subjects')

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'children':
            db_field.verbose_name = 'groups'
        return super().formfield_for_dbfield(db_field, **kwargs)

    def default_subjectgroup(self):
        return self.model.objects.filter(is_default=True).exists()

    def get_deleted_objects(self, objs, request):
        """
        Hook for customizing the delete process for the delete view and the  "delete selected" action.
        """
        if isinstance(objs, list):
            if objs[0].is_default:
                raise DeleteDefaultSubjectGroupException()
            return super().get_deleted_objects(objs, request)

        if objs.filter(is_default=True).exists():
            raise DeleteDefaultSubjectGroupException()
        return super().get_deleted_objects(objs, request)

    def get_changelist_formset(self, request, **kwargs):
        if request.method == 'POST':
            defaults = {
                'formfield_callback': partial(self.formfield_for_dbfield, request=request),
                **kwargs,
            }
            return modelformset_factory(
                self.model, self.get_changelist_form(request), formset=ModelFormSet,  extra=0,
                fields=self.list_editable, **defaults)
        return super(SubjectGroupAdmin, self).get_changelist_formset(request, **kwargs)

    @staticmethod
    def clear_existing_message(request):
        storage = messages.get_messages(request)
        for _ in storage:
            pass

    @transaction.atomic
    def changelist_view(self, request, extra_context=None):
        url_path = request.get_full_path()
        try:
            response = super(SubjectGroupAdmin, self).changelist_view(
                request, extra_context)
        except IntegrityError:
            msg = _("Warning: A default subject group has already been set.")
            self.message_user(request, msg, level=messages.WARNING)
            return HttpResponseRedirect(url_path)
        except DeleteDefaultSubjectGroupException:
            msg = _("Warning: Cannot delete the default subject group.")
            self.message_user(request, msg, level=messages.WARNING)
            return HttpResponseRedirect(url_path)
        except SubjectGroupException:
            msg = _("Warning: A default subject group is required.")
            self.message_user(request, msg, level=messages.WARNING)
            return HttpResponseRedirect(url_path)
        else:
            if request.method == 'POST' and not self.default_subjectgroup():
                transaction.set_rollback(True)
                self.clear_existing_message(request)
                msg = _("Warning: A default subject group is required.")
                self.message_user(request, msg, level=messages.WARNING)
                return HttpResponseRedirect(url_path)
            return response

    def delete_view(self, request, object_id, extra_context=None):
        try:
            template_response = super()._delete_view(
                request, object_id, extra_context=None)
        except SubjectGroupException:
            url_path = reverse('admin:observations_subjectgroup_change', kwargs={
                               'object_id': object_id})
            msg = _("Warning: Cannot delete the default subject group.")
            self.message_user(request, msg, level=messages.WARNING)
            return HttpResponseRedirect(url_path)
        else:
            return template_response


@admin.register(models.SourceGroup)
class SourceGroupAdmin(HierarchyModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        (None, {'fields': ('name', 'id')}),
        (_('Sources in Group'),
         {'fields': ('sources',)}),
        (_('Permissions'), {'fields': ('permission_sets',)}),
        (_('Member Source Groups'), {'fields': ('children',)}),
    )
    filter_horizontal = ('children', 'permission_sets', 'sources')


class RadioStatusFilter(admin.SimpleListFilter):
    title = 'Radio Status'
    parameter_name = 'radiostatus'

    def lookups(self, request, model_admin):
        return (
            ('online_gps', 'Green'),
            ('online_nogps', 'Blue'),
            ('offline', 'Offline'),
            ('alarm', 'Red'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'online_gps':
            return queryset.filter(radio_state='online-gps')
        elif value == 'online_nogps':
            return queryset.filter(radio_state='online')
        elif value == 'offline':
            return queryset.filter(radio_state='offline')
        elif value == 'alarm':
            return queryset.filter(radio_state='alarm')

        return queryset


class SourceTypeFilter(admin.SimpleListFilter):
    title = 'Source Type'
    parameter_name = 'source_type'

    def lookups(self, request, model_admin):
        source_types = [('trbonet', 'TRBOnet Radios')]
        for sourcetype in SOURCE_TYPES:
            source_types.append(sourcetype)
        return sorted(source_types, key=lambda item: item[1])

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            if value == 'trbonet':
                display = queryset.filter(
                    subject__subjectsource__assigned_range__contains=F(
                        'recorded_at'),
                    subject__subjectsource__source__manufacturer_id__startswith='trbonet-')
            else:
                display = queryset.filter(
                    subject__subjectsource__assigned_range__contains=F(
                        'recorded_at'),
                    subject__subjectsource__source__source_type=value)
            return display
        return queryset


@admin.register(models.SubjectStatus)
class SubjectStatusAdmin(OSMGeoExtendedAdmin):
    gis_geometry_field_name = 'location'
    search_fields = (
        'subject__name', 'subject__subjectsource__source__manufacturer_id')
    ordering = ('-recorded_at', 'subject',)
    # change_list_template = 'admin/subject_status_change_list.html'
    # readonly_fields = ('recorded_at', 'subject','delay_hours', 'additional')
    list_display = ('_status', 'radio_state_at', '_age_of_state',
                    'subject_link', '_recorded_at', '_location', '_age',
                    '_source_provider', '_source_type', )
    list_filter = (RadioStatusFilter, SourceTypeFilter,
                   'subject__subject_subtype__display',
                   SSSourceProviderFilter
                   )
    list_display_links = None  # Disable all links

    actions = None  # Disable all actions.

    def subject_link(self, obj):
        return mark_safe('<a href="{}">{}</a>'.format(
            reverse("admin:observations_subject_change",
                    args=(obj.subject.pk,)),
            obj.subject.name
        ))

    subject_link.short_description = 'Subject'
    subject_link.admin_order_field = 'subject'

    def _age(self, o):
        return humanize.naturaldelta(datetime.now(tz=pytz.utc) - o.recorded_at) if o.recorded_at else 'n/a'
    _age.short_description = _('Age of Observation')
    _age.admin_order_field = '-recorded_at'

    def _age_of_state(self, o):
        return humanize.naturaldelta(datetime.now(tz=pytz.utc) - o.radio_state_at) if o.radio_state_at else 'n/a'
    _age_of_state.short_description = _('Age of State')
    _age_of_state.admin_order_field = '-radio_state_at'

    def _status(self, o):
        state_desc = o.additional.get('state', '')
        if state_desc:
            state_desc = state_desc.capitalize()
            state_desc = f"{state_desc} w/GPS" if o.additional.get(
                'gps_fix') else state_desc
        else:
            state_desc = f"{o.subject.subject_subtype.display}"
        return mark_safe(f'<img src="{o.subject.image_url}" style="height:1.8em;float:right;" alt="{state_desc}"/>')
    _status.short_description = _('Map Marker')
    _status.admin_order_field = 'state_order'  # , 'additional__gps_fix')

    def get_queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectStatusAdmin, self).get_queryset(request)
        subject_source = models.SubjectSource.objects.filter(
            subject_id=OuterRef('subject__pk'))
        qs = qs.filter(delay_hours=0)
        qs = qs.annotate(subject_provider=Subquery(subject_source.values('source__provider__display_name')[:1]),
                         source_type=Subquery(subject_source.values('source__source_type')[:1]))
        qs = qs.select_related('subject', 'subject__subject_subtype')
        return qs

    def _location(self, o):
        return f'{o.location.x:0.4} / {o.location.y:0.4}'
    _location.short_description = 'Longitude / Latitude'
    _location.admin_order_field = 'location'

    def _recorded_at(self, o):
        return o.recorded_at
    _recorded_at.short_description = 'recorded at %s' % TIMEZONE_USED
    _recorded_at.admin_order_field = 'recorded_at'

    def _source_provider(self, o):
        return o.subject_provider

    _source_provider.admin_order_field = 'source'

    def _source_type(self, o):
        return o.source_type


class JsonAgg(Aggregate):
    function = 'jsonb_agg'
    template = '%(function)s(to_jsonb(%(expressions)s))'


@admin.register(models.SourceProvider)
class SourceProviderAdmin(admin.ModelAdmin):
    search_fields = ('provider_key', 'display_name',)
    ordering = ('provider_key', 'display_name')
    list_display = ('provider_key', 'display_name',)
    form = SourceProviderForm

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('provider_key', 'display_name', 'notes')
        }
        ),
        ('Provider configurations', {
            'classes': ('wide',),
            'fields': ('lag_notification_threshold',
                       'silence_notification_threshold',
                       'default_silent_notification_threshold',
                       'days_data_retain',
                       'two_way_messaging',
                       'messaging_config')
        }
        ),
        ('Advanced configuration', {
            'classes': ('wide', 'collapse',),
            'fields': ('additional',)
        }
        ),

        ('Subject Details Configuration', {
            'classes': ('wide', 'collapse',),
            'fields': ('transformation_rule', 'transforms')
        }
        )
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        if 'transforms' in form.changed_data:
            transaction.on_commit(lambda: [maintain_subjectstatus_for_subject.apply_async(args=[o.subject_id], kwargs={'notify': True})
                                           for o in models.SubjectSource.objects.filter(source__provider=obj)])


# @admin.register(models.SubjectSummary)


class SubjectSummaryAdmin(admin.ModelAdmin):
    change_list_template = 'admin/subject_summary_change_list.html'
    date_hierarchy = 'updated_at'

    list_filter = ('subject_subtype__subject_type__display',)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context
        )

        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response

        metrics = {
            'total': Count('id'),
        }

        response.context_data['summary'] = list(
            qs.values('subject_subtype__display')
            .annotate(**metrics)
            .order_by('-total')
        )

        response.context_data['summary_total'] = dict(
            qs.aggregate(**metrics)
        )

        period = get_next_in_date_hierarchy(
            request, self.date_hierarchy
        )
        summary_over_time = qs.annotate(
            period=Trunc(
                'updated_at',
                period,
                output_field=DateTimeField(),
            ),

        ).values('period').annotate(total=Count('id')).order_by('period')

        summary_range = summary_over_time.aggregate(
            low=Min('total'),
            high=Max('total'),
        )
        high = summary_range.get('high', 0)
        low = summary_range.get('low', 0)

        response.context_data['summary_over_time'] = [{
            'period': x['period'],
            'total': x['total'] or 0,
            'pct':
            ((x['total'] or 0) - low) / (high - low) * 100
            if high > low else 0,
        } for x in summary_over_time]

        return response


# @admin.register(models.SubjectPositionSummary)
class SubjectPositionSummaryAdmin(admin.ModelAdmin):
    change_list_template = 'admin/subject_position_change_list.html'
    date_hierarchy = 'recorded_at'
    # list_filter = ('subject_subtype__subject_type__display',)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context
        )

        try:
            response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response

        window_asc = {
            'partition_by': [F('source__subjectsource__subject'), ],
            'order_by': [F('recorded_at').asc(), ],
        }
        window_desc = {
            'partition_by': [F('source__subjectsource__subject'), ],
            'order_by': [F('recorded_at').desc(), ],
        }

        end = datetime.now(tz=pytz.utc)
        start = end - timedelta(days=30)

        o = models.Observation.objects.filter(
            source__subjectsource__assigned_range__contains=F('recorded_at'),
            recorded_at__gte=start, recorded_at__lt=end, ).exclude(
            location=models.EMPTY_POINT).annotate(
            subject_name=F('source__subjectsource__subject__name'),
            subject_id=F('source__subjectsource__subject__id'),
            subject_subtype=F(
                'source__subjectsource__subject__subject_subtype'),
            latest_location=Window(expression=FirstValue(
                F('location')), **window_desc),
            latest_additional=Window(expression=FirstValue(
                F('additional')), **window_desc),
            latest_recorded_at=Window(expression=FirstValue(F('recorded_at')), **window_desc))\
            .order_by('subject_name', 'subject_id').distinct('subject_name', 'subject_id')

        response.context_data['subject_position_endpoints'] = o.values()

        return response


def get_next_in_date_hierarchy(request, date_hierarchy):
    if date_hierarchy + '__day' in request.GET:
        return 'hour'
    if date_hierarchy + '__month' in request.GET:
        return 'day'
    if date_hierarchy + '__year' in request.GET:
        return 'week'
    return 'month'


@admin.register(models.SubjectMaximumSpeed)
class ObservationAnnotatorAdmin(admin.ModelAdmin):

    list_display = ('subject_name', 'max_speed', 'subject_subtype',)
    list_editable = ('max_speed',)
    search_fields = ('subject__name',)
    list_filter = ('max_speed', 'subject__subject_subtype__display',
                   'subject__subject_subtype__subject_type__display',)
    ordering = ('subject', 'max_speed', )
    readonly_fields = ('id',)

    def subject_name(self, o):
        return o.subject.name
    subject_name.admin_order_field = 'subject'

    def subject_subtype(self, o):
        return o.subject.subject_subtype.value


class SubjectMessagesFilter(SimpleListFilter):
    title = 'Subjects'
    parameter_name = 'subjects'

    def lookups(self, request, model_admin):

        # Get subjects with messages and add as filter options
        sender_subject_ids = models.Message.objects.filter(sender_content_type__model="subject").values_list(
            'sender_id', flat=True)
        receiver_subject_ids = models.Message.objects.filter(receiver_content_type__model="subject").values_list(
            'receiver_id', flat=True)
        subject_ids = receiver_subject_ids.union(sender_subject_ids)
        subjects = models.Subject.objects.filter(id__in=subject_ids)

        return [(str(k.id), k.name) for k in subjects]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(Q(sender_id=value) | Q(receiver_id=value))
        return queryset


@admin.register(models.Message)
class MessageAdmin(OSMGeoExtendedAdmin):
    gis_geometry_field_name = "device_location"
    list_display = ('sender', 'receiver', 'message_type',
                    'status', 'message_time', 'read')
    list_editable = ('read',)
    form = MessagesForm
    search_fields = ('sender_id', 'receiver_id')
    list_filter = (SubjectMessagesFilter,)
    ordering = ('message_time', )
    readonly_fields = ('id',)
    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('sender_content_type', 'sender_id', 'receiver_content_type', 'receiver_id', 'device',
                        'message_type', 'text', 'status', 'device_location', 'message_time', 'read'))
        }
        ),
        ('Advanced Message Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional', 'id',)
        })
    )

    def get_search_results(self, request, queryset, search_term):
        qs = queryset
        queryset, use_distinct = super(MessageAdmin, self).get_search_results(
            request, qs, search_term)

        matching_subject_ids = models.Subject.objects.filter(
            name__icontains=search_term).values_list('id', flat=True)
        queryset |= qs.filter(Q(sender_id__in=matching_subject_ids) | Q(
            receiver_id__in=matching_subject_ids))
        return queryset, use_distinct

    def formfield_for_genericforeignkey(self, db_field, request, **kwargs):
        kwargs['widget'] = MessageGenericForeignKeyRawIdWidget(db_field.remote_field,
                                                               self.admin_site,
                                                               using=kwargs.get('using'))
        return db_field.formfield(**kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ["sender_id", "receiver_id"]:
            return self.formfield_for_genericforeignkey(db_field, request, **kwargs)
        return super(MessageAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
