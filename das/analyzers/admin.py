from django.contrib import admin
from django.contrib.admin import ModelAdmin
import analyzers.models as models

@admin.register(models.GeofenceAnalyzer)
class GeofenceAnalyzerAdmin(ModelAdmin):
    pass

@admin.register(models.SubjectAnalyzer)
class SubjectAnalyzerAdmin(admin.ModelAdmin):
    pass

