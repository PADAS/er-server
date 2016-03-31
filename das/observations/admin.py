from django.contrib import admin

import observations.models as models
import observations.forms
from observations.forms import SubjectForm
from core.admin import HierarchyModelAdmin

@admin.register(models.Subject)
class SubjectAdmin(admin.ModelAdmin):

    list_display = ['id', 'name', 'subject_type', 'subject_subtype',
                    'additional', 'group']
    search_fields=['name', 'subject_subtype']

    fields = ('id', 'name', 'additional', 'group', SubjectForm.SUBTYPE_FIELD)

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectAdmin, self).queryset(request)
        if request.user.is_superuser:
            return qs

        raise NotImplementedError('implement filtering SubjectAdmin to user permissions')
        return qs.filter(owner=request.user)

    form = observations.forms.SubjectForm

    def type_subtype_view(self, obj):
        if obj is not None:
            return '{}:{}'.format(obj.subject_type, obj.subject_subtype)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        form.base_fields[SubjectForm.SUBTYPE_FIELD].initial = self.type_subtype_view(obj)
        return form

    def save_model(self, request, obj, form, change):
        '''
        Hook to coerce type_subtype value to valid subject_type and subject_subtype model fields.
        '''
        if change and SubjectForm.SUBTYPE_FIELD in form.changed_data:
            (t, st) = form.cleaned_data.get(SubjectForm.SUBTYPE_FIELD).split(':')
            obj.subject_type = t
            obj.subject_subtype = st

        super().save_model(request, obj, form, change)


@admin.register(models.Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['id', 'source_type', 'manufacturer_id', 'model_name', 'additional']


@admin.register(models.SubjectSource)
class SubjectSourceAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Region)
class RegionAdmin(admin.ModelAdmin):
    fields = ['id', 'region', 'country', 'slug']

    def __str__(self):
        return self.slug

@admin.register(models.SubjectGroup)
class SubjectGroupAdmin(HierarchyModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(models.SourceGroup)
class SubjectGroupAdmin(HierarchyModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)


