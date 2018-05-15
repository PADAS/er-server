import random
from datetime import datetime

from django.contrib import admin
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminSplitDateTime
from django.contrib.postgres.forms import RangeWidget
from django.db.models import F

import observations.models as models
import observations.forms
from observations.forms import SubjectForm, SubjectChangeListForm, SubjectSourceForm
from core.admin import HierarchyModelAdmin
from utils.html import make_html_list

from django.contrib.postgres import fields
# from django_json_widget.widgets import JSONEditorWidget


from django.template.loader import render_to_string
from django.utils.html import format_html


admin.site.site_header = _('DAS Administration')
admin.site.site_title = _('DAS Administration')


@admin.register(models.SubjectCategory)
class SubjectCategoryAdmin(admin.ModelAdmin):
    list_display = ('value', 'display')
    list_editable = ('display', )
    readonly_fields = ('id', 'value',)
    search_fields = ('value', 'display')
    ordering = ('display',)


@admin.register(models.SubjectType)
class SubjectTypeAdmin(admin.ModelAdmin):
    list_display = ('category_display', 'value', 'display')
    list_editable = ('display', )
    list_filter = ('category__display',)
    readonly_fields = ('value', 'id')
    search_fields = ('value', 'display',
                     'category__display', 'category__value')

    ordering = ('category__display', 'display')
    list_display_links = ('value',)

    def category_display(self, o):
        return o.category.display


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
        ('Advanced Settings', {
            'classes': ('wide', 'collapse',),
            'fields': ('additional', 'id')
        }
        )
    )


@admin.register(models.Subject)
class SubjectAdmin(admin.ModelAdmin):

    list_display = ('name', 'subject_type',
                    'is_active', 'get_attributes', 'all_groups', 'all_sources')

    search_fields = ('name', 'subject_type__value', 'common_name__display',
                     'subjectsource__source__manufacturer_id')

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('id', 'name', 'subject_type', 'common_name',
                        'additional', 'groups',))
        }
        ),
    )
    list_filter = ('is_active', 'subject_type__category__value',
                   'subject_type__value', 'common_name')
    list_editable = ('subject_type', 'is_active',)
    readonly_fields = ('id',)
    list_per_page = 25
    ordering = ('name',)

    # def subject_type(self, o):
    #     return o.subject.subject_type.category.value

    def subject_type(self, o):
        return o.subject.subject_type

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

    actions = ['assign_random_color', ]

    inlines = [SubjectSourceInline, ]

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectAdmin, self).queryset(request)
        if request.user.is_superuser:
            return qs

        raise NotImplementedError(
            'implement filtering SubjectAdmin to user permissions')
        return qs.filter(owner=request.user)

    form = observations.forms.SubjectForm

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == 'common_name':
            kwargs['queryset'] = models.CommonName.objects.all()
        return super().formfield_for_foreignkey(db_field, request=request, **kwargs)

    def get_attributes(self, instance):
        context = dict((k, instance.additional[k]) for k in (
            'rgb', 'region', 'country', 'sex', 'age') if k in instance.additional)

        return ', '.join(': '.join((k, v)) for k, v in context.items())

    get_attributes.short_description = _('Attributes')

    def all_groups(self, instance):
        groups = instance.groups.all()
        return make_html_list(sorted(group.name for group in groups))

    all_groups.short_description = _('Groups')
    all_groups.allow_tags = True

    def all_sources(self, instance):
        subjectsources = models.SubjectSource \
            .objects \
            .filter(subject_id=instance.pk).annotate(manufacturer_id=F('source__manufacturer_id')) \
            .order_by('-assigned_range')

        content = render_to_string(
            'admin/subjectsource.html', {'subjectsources': list(subjectsources.values())})
        return format_html(content)

    all_sources.short_description = _('Sources')
    all_sources.allow_tags = True

    def get_changelist_form(self, request, **kwargs):
        return SubjectChangeListForm


@admin.register(models.CommonName)
class CommonNameAdmin(admin.ModelAdmin):
    list_display = ('value', 'display', 'subject_type')

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
    list_display = ['id', 'source_type',
                    'manufacturer_id', 'model_name', 'additional']
    search_fields = ('id', 'manufacturer_id', 'model_name')
    list_filter = ('source_type', 'model_name')
#    filter_horizontal = ('groups',)


@admin.register(models.SubjectSource)
class SubjectSourceAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'manufacturer_id',
                    'display_assigned_range')
    list_filter = ('subject__subject_type__value', 'source__source_type')
    search_fields = ('source__manufacturer_id', 'subject__name')
    readonly_fields = ('id',)

    def subject_name(self, o):
        return o.subject.name

    def manufacturer_id(self, o):
        return o.source.manufacturer_id

    def display_assigned_range(self, o):

        d1, d2 = o.assigned_range.lower, o.assigned_range.upper
        if d1.year >= 9999:
            d1 = '-'
        if d2.year >= 9999:
            d2 = '-'

        return d1, d2

    # formfield_overrides = {
    #     models.DateTimeRangeField : {
    #         'widget': RangeWidget(AdminSplitDateTime)
    #     }
    # }

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
        ('Advanced', {
            'classes': ('wide', 'collapse'),
            'fields': ('additional',)
        }
        )
    )


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

    list_filter = ('delay_hours', 'subject__subject_type__value')


@admin.register(models.SourceProvider)
class SourceProviderAdmin(admin.ModelAdmin):
    search_fields = ('provider_key', 'display_name',)
    ordering = ('provider_key',)
    list_display = ('provider_key', 'display_name',)
