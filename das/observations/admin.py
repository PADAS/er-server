from django.contrib import admin
from mptt.admin import MPTTModelAdmin
from mptt.forms import TreeNodeMultipleChoiceField

import observations.models as models

# Register your models here.


@admin.register(models.Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'subject_type', 'additional']

    def queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super(SubjectAdmin, self).queryset(request)
        if request.user.is_superuser:
            return qs

        raise NotImplementedError('implement filtering SubjectAdmin to user permissions')
        return qs.filter(owner=request.user)


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
class SubjectGroupAdmin(MPTTModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)


