from django.contrib import admin
import observations.models as models

# Register your models here.

@admin.register(models.Subject)
class SubjectAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Region)
class RegionAdmin(admin.ModelAdmin):
    fields = ['id', 'region', 'country', 'slug']



