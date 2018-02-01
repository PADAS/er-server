from django.contrib import admin
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.contrib.admin.widgets import FilteredSelectMultiple

import observations.models as models
import observations.forms
from observations.forms import SubjectForm
from core.admin import HierarchyModelAdmin
from utils.html import make_html_list


@admin.register(models.Subject)
class SubjectAdmin(admin.ModelAdmin):

    list_display = ('id', 'name', 'subject_type', 'subject_subtype',
                    'is_active', 'additional', 'all_groups', 'all_sources')

    search_fields = ('name', 'subject_subtype', 'common_name__display')

    fields = ('id', 'name', 'common_name', 'additional',
              'groups', SubjectForm.SUBTYPE_FIELD)
    list_filter = ('is_active', 'subject_type',
                   'subject_subtype', 'common_name')
    list_editable = ('is_active',)

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectAdmin, self).queryset(request)
        if request.user.is_superuser:
            return qs

        raise NotImplementedError(
            'implement filtering SubjectAdmin to user permissions')
        return qs.filter(owner=request.user)

    form = observations.forms.SubjectForm

    def type_subtype_view(self, obj):
        if obj is not None:
            return '{}:{}'.format(obj.subject_type, obj.subject_subtype)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        form.base_fields[SubjectForm.SUBTYPE_FIELD].initial = self.type_subtype_view(
            obj)
        return form

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == 'common_name':
            kwargs['queryset'] = models.CommonName.objects.all()
        return super().formfield_for_foreignkey(db_field, request=request, **kwargs)

    def all_groups(self, instance):
        groups = instance.groups.all()
        return make_html_list(sorted(group.name for group in groups))

    all_groups.short_description = 'Groups'
    all_groups.allow_tags = True

    def all_sources(self, instance):
        subjectsources = models.SubjectSource \
            .objects \
            .filter(subject_id=instance.pk) \
            .order_by('-assigned_range')

        return make_html_list(sorted('{} {}'.format(
            str(ss.assigned_range.upper), str(ss.source_id)) for ss in subjectsources))

    all_sources.short_description = 'Sources'
    all_sources.allow_tags = True

    def save_model(self, request, obj, form, change):
        '''
        Hook to coerce type_subtype value to valid subject_type and subject_subtype model fields.
        '''
        if change and SubjectForm.SUBTYPE_FIELD in form.changed_data:
            (t, st) = form.cleaned_data.get(
                SubjectForm.SUBTYPE_FIELD).split(':')
            obj.subject_type = t
            obj.subject_subtype = st

        super().save_model(request, obj, form, change)


@admin.register(models.CommonName)
class CommonNameAdmin(admin.ModelAdmin):
    list_display = ('value', 'display', 'subject_subtype')

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectAdmin, self).queryset(request)
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
    list_filter = ('subject__subject_subtype', 'source__source_type')
    search_fields = ('source__manufacturer_id', 'subject__name')
    pass


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

    list_filter = ('delay_hours', 'subject__subject_subtype')


@admin.register(models.SourceProvider)
class SourceProviderAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)
    list_display = ('name',)
