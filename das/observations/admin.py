import random
import csv
from datetime import datetime, timedelta
import pytz

from django.contrib import admin

from django.conf import settings

from django.contrib.admin.widgets import FilteredSelectMultiple, RelatedFieldWidgetWrapper

from django import forms
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _

from django.db.models import Q, F, Count, Value, ExpressionWrapper, Avg, Window, Max, Sum, Min

from django.db.models.functions import FirstValue, LastValue, Trunc
from django.db.models import BooleanField, OuterRef, Subquery, DateTimeField

from django.db.models.functions import Now
from django.http import HttpResponse

import observations.models as models
import observations.forms
from observations.forms import SubjectForm, SubjectChangeListForm, SubjectSourceForm

from core.admin import HierarchyModelAdmin
from utils.html import make_html_list

from django.template.loader import render_to_string
from django.utils.html import format_html

admin.site.site_header = _('DAS Administration')
admin.site.site_title = _('DAS Administration')
admin.site.index_title = _('DAS Administration')


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


class SubjectSubTypeInline(admin.TabularInline):
    model = models.SubjectSubType

    verbose_name = _('Subject Sub-Type')
    verbose_name_plural = _('Subject Sub-Types')
    show_change_link = False

    readonly_fields = ('value',)

    fields = ('value', 'display', )

    ordering = ('display',)

    extra = 1

    def get_extra(self, request, obj=None, **kwargs):
        # This allows me to override the 'number of extra inline forms' if the
        # containing object already exists.
        if obj:
            return 0
        return self.extra


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


class SubjectSourceInline(admin.StackedInline):
    model = models.SubjectSource
    max_num = 1

    can_delete = True
    verbose_name = _('Source Assignment')
    verbose_name_plural = _('Source Assignment')
    show_change_link = True
    fk_name = 'subject'

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
            'classes': ('wide',),
            'fields': ('data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason')
        }
        ),
        ('Advanced Settings', {
            'classes': ('wide', 'collapse',),
            'fields': ('additional', 'id')
        }
        )
    )


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


from django.contrib.postgres.aggregates import ArrayAgg


@admin.register(models.Subject)
class SubjectAdmin(ExportCsvMixin, admin.ModelAdmin):

    list_display = ('name', 'subject_subtype',
                    '_is_active', 'get_attributes', 'all_groups', 'all_sources',)

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
            'fields': (('rgb', 'sex', 'country', 'region',))
        }
        ),
        ('Advanced Subject Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional', 'created_at', 'updated_at',)
        })
    )
    list_filter = ('is_active', GroupAssignedFilter,
                   'subject_subtype__subject_type__display',
                   'subject_subtype__display',
                   )
    list_editable = ('subject_subtype',)
    readonly_fields = ('id', 'created_at', 'updated_at',)
    list_per_page = 25
    ordering = ('name',)

    def _is_active(self, o):
        return o.is_active

    _is_active.short_description = 'Active?'
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
        qs = qs.annotate(groups_names=ArrayAgg('groups__name'))
        return qs

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

    form = observations.forms.SubjectFormWithAttributes
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
        return make_html_list(instance.groups_names)

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
            .filter(subject_id=instance.pk).annotate(manufacturer_id=F('source__manufacturer_id')) \
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
            'admin/subjectsource.html', {'subjectsources': list(subjectsources)})

        return format_html(content)

    all_sources.short_description = _('Source Assignments')
    all_sources.allow_tags = True

    def get_changelist_form(self, request, **kwargs):
        return SubjectChangeListForm

    def change_view(self, request, object_id, form_url='', extra_context=None):

        extra_context = extra_context or {}
        latest_observations = models.Observation.objects.filter(source__subjectsource__subject__id=object_id).order_by(
            '-recorded_at').values('recorded_at', 'location', 'additional')
        extra_context['observations'] = latest_observations[:10]

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


@admin.register(models.Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['manufacturer_id', 'source_type',
                    'model_name', 'get_attributes']
    search_fields = ('id', 'manufacturer_id', 'model_name', 'additional')
    list_filter = ('source_type', 'model_name')
    readonly_fields = ('id', 'created_at', 'updated_at',)
#    filter_horizontal = ('groups',)

    form = observations.forms.SourceForm
    fieldsets = (
        (None, {
            'fields': ('manufacturer_id', 'source_type', 'model_name', 'provider',)
        }
        ),
        ('Source Attributes', {
            'classes': ('wide',),
            'fields': ('collar_status', 'collar_model', 'has_acc_data', 'data_owners', 'adjusted_beacon_freq')
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

        d1, d2 = o.assigned_range.lower, o.assigned_range.upper
        if d1.year >= 9999:
            d1 = '-'
        if d2.year >= 9999:
            d2 = '-'

        return d1, d2

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
            'fields': ('data_status', 'data_starts_source', 'data_stops_source', 'data_stops_reason')
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
    subjects = forms.ModelMultipleChoiceField(
        queryset=models.Subject.objects.by_is_active(True),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Subjects'),
            is_stacked=False
        )
    )

    class Meta:
        model = models.SubjectGroup
        fields = ('name', 'id', 'subjects', 'children', 'permission_sets')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['children'].queryset = models.SubjectGroup.objects.exclude(
            id__exact=self.instance.id)


@admin.register(models.SubjectGroup)
class SubjectGroupAdmin(HierarchyModelAdmin):
    form = SubjectGroupChangeForm
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        (None, {'fields': ('name', 'id')}),
        (_('Members'), {'fields': ('subjects', 'children',)}),
        (_('Permissions'), {'fields': ('permission_sets',)}),

    )
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


@admin.register(models.SubjectStatus)
class SubjectStatusAdmin(admin.ModelAdmin):
    search_fields = ('subject__name',)
    ordering = ('-recorded_at',)

    list_display = ('subject', 'delay_hours', 'recorded_at', 'location')

    list_filter = ('delay_hours', 'subject__subject_subtype__value')


@admin.register(models.SourceProvider)
class SourceProviderAdmin(admin.ModelAdmin):
    search_fields = ('provider_key', 'display_name',)
    ordering = ('provider_key',)
    list_display = ('provider_key', 'display_name',)


@admin.register(models.SubjectSummary)
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


def get_next_in_date_hierarchy(request, date_hierarchy):
    if date_hierarchy + '__day' in request.GET:
        return 'hour'
    if date_hierarchy + '__month' in request.GET:
        return 'day'
    if date_hierarchy + '__year' in request.GET:
        return 'week'
    return 'month'
