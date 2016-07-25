from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.conf import settings
import analyzers.models as models

if settings.DEBUG:

    @admin.register(models.GeofenceAnalyzer)
    class GeofenceAnalyzerAdmin(ModelAdmin):
        pass

    @admin.register(models.SubjectAnalyzer)
    class SubjectAnalyzerAdmin(admin.ModelAdmin):
        pass

