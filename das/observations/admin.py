import random
import csv
from datetime import datetime, timedelta
from uuid import UUID
import urllib

import pytz
import humanize
from django.contrib import admin
from django.db import connection
from django.conf import settings
from django.urls import reverse
from django.core.paginator import Paginator
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.contenttypes.admin import GenericTabularInline
from django import forms
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q, F, Count, ExpressionWrapper, Window, Max, Min
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models.functions import FirstValue, Trunc
from django.db.models import BooleanField, OuterRef, Subquery, DateTimeField
from django.db.models.functions import Now
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.db.models.expressions import RawSQL
import django.contrib.gis.admin as gis_admin
from django.utils.safestring import mark_safe
from django.utils.functional import cached_property

import observations.models as models
from tracking.models import SourcePlugin
import observations.forms
from observations.forms import SubjectChangeListForm, SubjectSourceForm, SourceProviderForm
from observations.utils import assigned_range_dates
from core.admin import HierarchyModelAdmin, InlineExtraDynamicMixin, \
    SaveCoordinatesToCookieMixin
from core.openlayers import OSMGeoExtendedAdmin
from core.common import TIMEZONE_USED
from utils.html import make_html_list
from .models import SOURCE_TYPES
from observations.daterange_filter import DateRangeFilter
from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple
from observations.forms import ObservationForm

site_title = _('DAS Administration (advanced view)')
admin.site.site_title = site_title
admin.site.site_header = site_title
admin.site.index_title = site_title

admin.site.index_template = 'admin/standard_admin_index.html'

OBSERVATIONS_HISTORY_LIMIT = timedelta(days=90)


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
            uuid_version = UUID(uuid).version
        except ValueError:
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
    ordering = ('display',)

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

    ordering = ('subject_type', 'display')
    list_display_links = ('value',)

    fieldsets = (
        (None,
         {'fields': (('display', 'value', 'subject_type'))}
         ),
    )


class SubjectSourceInline(InlineExtraDynamicMixin, admin.StackedInline):
    model = models.SubjectSource

    can_delete = True
    verbose_name = _('Source Assignment')
    verbose_name_plural = _('Source Assignments')
    show_change_link = True
    fk_name = 'subject'
    readonly_fields = ('additional', )
    template = 'admin/observations/subjectsource/edit_inline/stacked.html'

    form = SubjectSourceForm

    fieldsets = (
        (None, {
            'fields': (('subject', 'source',),)
        }
        ),
        (None, {
            'classes': ('wide',),
            'fields': ('assigned_range',)
        }
        ),
        ('Source Assignment Attributes', {
            'classes': ('wide', 'collapse',),
            'fields': ('chronofile', 'data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason', 'comments')
        }
        ),
        ('Raw Attributes Data', {
            'classes': ('wide', 'collapse',),
            'fields': ('additional', 'id')
        }
        )
    )


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
                Q(source__subjectsource__subject__name=self.value(), )
            )


class SubjectIdFilter(InputFilter, ValidateFilterMixin):
    parameter_name = 'subject_id'
    title = _('Subject ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            uuid = self.check_uuid(self.value())
            return queryset.filter(
                Q(source__subjectsource__subject_id=uuid, )
            )


class LargeTablePaginator(Paginator):
    '''
    If the query has no filter, then get count from pg_class.
    '''

    def _get_count(self):
        # Handle subsequent calls in same request.
        if getattr(self, '_count', None) is not None:
            return self._count

        query = self.object_list.query
        self._count = None

        if not query.where:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT reltuples FROM pg_class WHERE relname = %s",
                                   [query.model._meta.db_table])
                    self._count = int(cursor.fetchone()[0])
            except:
                pass

        return self._count if self._count is not None else super().count

    count = cached_property(_get_count)

@admin.register(models.Observation)
class ObservationAdmin(ExportCsvMixin, ValidateFilterMixin, OSMGeoExtendedAdmin):
    # form = ObservationForm
    readonly_fields = ("created_at", "id")
    fields = ("id", "recorded_at", "created_at",
              "location", "exclusion_flags", "source", "additional")
    list_display = ('subject_link', '_manufacturer_id', '_recorded_at', '_created_at',
                    '_longitude', '_latitude', '_state', '_event_action', 'exclusion_flags')
    list_editable = ('exclusion_flags',)
    list_display_links = None
    show_full_result_count = False
    autocomplete_fields = ('source',)

    paginator = LargeTablePaginator
    formfield_overrides = {
        BitField: {
            'widget': BitFieldCheckboxSelectMultiple
        },
    }

    gis_geometry_field_name = 'location'

    list_filter = (SubjectNameFilter, SubjectIdFilter, ('recorded_at', DateRangeFilter))

    def subject_link(self, obj):
        return mark_safe('<a href="{}">{}</a>'.format(
            reverse("admin:observations_subject_change",
                    args=(obj.subject_id,)),
            obj.subject_name
        ))

    subject_link.short_description = 'Subject'

    def _longitude(self, o):
        return round(o.location.x, 5)
    _longitude.short_description = _('Longitude')

    def _latitude(self, o):
        return round(o.location.y, 5)
    _latitude.short_description = _('Latitude')

    def _state(self, o):
        return o.additional.get('radio_state')
    _state.short_description = 'Radio Status'

    def _event_action(self, o):
        return o.additional.get('event_action')
    _event_action.short_description = 'Event Action'

    def _subject_name(self, o):
        return o.subject_name

    def _manufacturer_id(self, o):
        return o.manufacturer_id

    def _created_at(self, o):
        return o.created_at
    _created_at.short_description = 'row created at %s' % TIMEZONE_USED
    _created_at.admin_order_field = 'created_at'

    def _recorded_at(self, o):
        recorded_at = o.recorded_at.strftime("%d %b, %Y, %H:%M")
        return mark_safe(
            f'<a href="{reverse("admin:observations_observation_change", args=(o.id,))}">{recorded_at}</a>'
        )
    _recorded_at.short_description = 'recorded at %s' % TIMEZONE_USED
    _recorded_at.admin_order_field = 'recorded_at'
    _recorded_at.admin_order_first_type = "desc"

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_queryset(self, request):
        qs = super(ObservationAdmin, self).get_queryset(request)

        if self.is_change_view(request):
            return qs

        # Reference Subject to get Name.
        # TODO: Consider a raw query.
        subject = models.Subject.objects.filter(subjectsource__source_id=OuterRef('source_id'),
                                                subjectsource__assigned_range__contains=OuterRef('recorded_at'))
        qs = qs.annotate(subject_name=Subquery(subject.values('name')[:1]))

        qs = qs.annotate(manufacturer_id=F('source__manufacturer_id'),
                         subject_name=F(
                             'source__subjectsource__subject__name'),
                         subject_id=F('source__subjectsource__subject__id')
                         )
        qs = qs.select_related('source',)

        # Hard-limit at 180 days.
        dt = datetime.now(tz=pytz.utc) - OBSERVATIONS_HISTORY_LIMIT
        if not self.is_date_range_set(request):
            qs = qs.filter(recorded_at__gte=dt)

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
            extra_context['history_limit_days'] = self.difference_in_date( d1[0], d2[0])
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


@admin.register(models.Subject)
class SubjectAdmin(ExportCsvMixin, admin.ModelAdmin):

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
        qs = qs.annotate(groups_names=ArrayAgg('groups__name'))\
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
            .order_by('-assigned_range').annotate(current=ExpressionWrapper(Q(assigned_range__contains=Now()), output_field=BooleanField())

                                                  )

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

    def change_view(self, request, object_id, form_url='', extra_context=None):

        extra_context = extra_context or {}
        latest_observations = models.Observation.objects.filter(
            source__subjectsource__subject__id=object_id,
            source__subjectsource__assigned_range__contains=F('recorded_at')).order_by('-recorded_at')\
            .values('source__manufacturer_id', 'recorded_at', 'location', 'additional')
        extra_context['observations'] = latest_observations[:25]
        extra_context['timezone'] = TIMEZONE_USED

        extra_context['subject_id'] = str(object_id)
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context,
        )


@admin.register(models.CommonName)
class CommonNameAdmin(admin.ModelAdmin):
    list_display = ('value', 'display', 'subject_subtype')

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(CommonNameAdmin, self).queryset(request)
        if request.user.is_superuser:
            return qs

        raise NotImplementedError(
            'implement filtering SubjectAdmin to user permissions')
        return qs.filter(owner=request.user)


@admin.register(models.SubjectSourceSummary)
class SubjectSourceSummaryAdmin(admin.ModelAdmin):
    list_display = ('source', '_subject', '_source_plugin',
                    '_plugin', '_provider', '_start_date', '_end_date')
    list_filter = ('source__provider__display_name',)
    search_fields = ('source__manufacturer_id', 'subject__name',
                     'source__provider__display_name')
    ordering = ('source', )

    def record_link(self, url, key, view):
        return mark_safe('<a href="{}">{}</a>'.format(
            reverse(url, args=(key,)), view
        ))

    def _subject(self, o):
        return self.record_link("admin:observations_subject_change", o.subject.id, o.subject)

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
            'fields': ('chronofile', 'data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason', 'comments')
        }
        ),
        ('Advanced', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional',)
        }
        )
    )


@admin.register(models.Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['manufacturer_id', 'source_type',
                    'model_name', 'get_attributes', '_source_provider', ]
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
                       'collar_manufacturer', 'data_owners',
                       'adjusted_beacon_freq', 'frequency',
                       'adjusted_frequency',
                       'backup_frequency', 'predicted_expiry',
                       'feed_id', 'feed_passwd'
                       )
        }
        ),
        ('Data Source Configuration', {
            'classes': ('wide',),
            'fields': ('silence_notification_threshold',)
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
    list_filter = ('source__source_type', CurrentAssignmentFilter,
                   'subject__subject_subtype__subject_type__value', 'subject__subject_subtype__value')
    search_fields = ('source__manufacturer_id', 'subject__name')
    readonly_fields = ('id',)

    def subject_name(self, o):
        return o.subject.name

    def manufacturer_id(self, o):
        return o.source.manufacturer_id

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
            'fields': ('chronofile', 'data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason', 'comments')
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


from django.contrib.auth import get_permission_codename
from accounts.models import PermissionSet


@admin.register(models.SubjectGroup)
class SubjectGroupAdmin(HierarchyModelAdmin):
    form = SubjectGroupChangeForm
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        (None, {'fields': ('name', 'id', 'is_visible')}),
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
    list_display = ('name', 'is_visible')
    list_editable = ('is_visible',)
    list_filter = ('is_visible',)
    filter_horizontal = ('children', 'permission_sets', 'subjects')


    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'children':
            db_field.verbose_name = 'groups'
        return super().formfield_for_dbfield(db_field, **kwargs)


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
        return source_types

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
    ordering = ('-recorded_at',)
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
        qs = qs.filter(delay_hours=0)
        qs = qs.annotate(state_order=RawSQL(
            '''jsonb_extract_path_text(observations_subjectstatus.additional, 'state')
             || jsonb_extract_path_text(observations_subjectstatus.additional, 'gps_fix')''', ()))
        qs = qs.prefetch_related('subject')
        qs = qs.annotate(
            provider_name=F('subject__subjectsource__source__provider__display_name'))
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
        return o.provider_name

    def _source_type(self, o):
        source = None
        try:
            source = o.subject.source.source_type
        except Exception:
            pass
        return source


@admin.register(models.SourceProvider)
class SourceProviderAdmin(admin.ModelAdmin):
    search_fields = ('provider_key', 'display_name',)
    ordering = ('provider_key',)
    list_display = ('provider_key', 'display_name',)
    readonly_fields = ('id',)
    form = SourceProviderForm

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('provider_key', 'display_name', 'notes')
        }
        ),
        ('Provider configurations', {
            'classes': ('wide',),
            'fields': ('lag_notification_threshold', 'silence_notification_threshold', 'days_data_retain')
        }
        ),

        ('Advanced configuration', {
            'classes': ('wide', 'collapse',),
            'fields': ('additional', 'id')
        }
        )
    )

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
            qs = response.context_data['cl'].queryset
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
    ordering = ('subject__name', )
    readonly_fields = ('id',)

    def subject_name(self, o):
        return o.subject.name

    def subject_subtype(self, o):
        return o.subject.subject_subtype.value
