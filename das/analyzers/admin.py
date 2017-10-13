from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.conf import settings
import analyzers.models as models


@admin.register(models.ObservationAnnotator)
class ObservationAnnotatorAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ImmobilityAnalyzerConfig)
class ImmobilityAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subject_group_name',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name


@admin.register(models.EnvironmentalSubjectAnalyzerConfig)
class EnvironmentalSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subject_group_name',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name


@admin.register(models.ProximityAnalyzerConfig)
class ProximitySubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subject_group_name',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name


@admin.register(models.GeofenceAnalyzerConfig)
class GeofenceSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subject_group_name',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name


@admin.register(models.LowSpeedWilcoxAnalyzerConfig)
class LowSpeedWilcoxSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subject_group_name',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name


@admin.register(models.LowSpeedPercentileAnalyzerConfig)
class LowSpeedPercentileSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subject_group_name',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name


@admin.register(models.SubjectSpeedProfile)
class SubjectSpeedProfileAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpeedDistro)
class SpeedDistroAdmin(admin.ModelAdmin):
    pass

