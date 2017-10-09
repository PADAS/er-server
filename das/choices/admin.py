import logging

from django.contrib import admin

import choices.models as models


@admin.register(models.Choice)
class ChoiceAdmin(admin.ModelAdmin):
    ordering = ('model', 'field', 'ordernum', 'display')
    list_display = ('model', 'field', 'value', 'display', 'ordernum')
    list_display_links = ('model', 'field')
    search_fields = ('model', 'field', 'value', 'display')
    list_editable = ('value', 'display', 'ordernum')


@admin.register(models.DynamicChoice)
class DynamicChoiceAdmin(admin.ModelAdmin):
    ordering = ('id', 'model_name')
    list_display = ('id', 'model_name', 'criteria')
    list_display_links = ('id',)
    search_fields = ('model_name',)


class BaseChoiceAdmin(admin.ModelAdmin):
    ordering = ('ordernum',)
    list_display = ('id', 'name', 'ordernum')
    list_display_links = ('id',)
    search_fields = ('name',)
    list_editable = ('name', 'ordernum')


@admin.register(models.SectionArea)
class SectionAreaAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Station)
class StationAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FenceLocation)
class FenceLocationAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FenceDamage)
class FenceDamageAdmin(admin.ModelAdmin):
    pass


@admin.register(models.KeySpecies)
class KeySpeciesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Species)
class SpeciesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AnimalSex)
class AnimalSexAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AnimalAge)
class AnimalAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CarcassAge)
class CarcassAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TrophyStatus)
class TrophyStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CauseOfDeath)
class CauseOfDeathAdmin(admin.ModelAdmin):
    pass


@admin.register(models.InjuryCause)
class InjuryCauseAdmin(admin.ModelAdmin):
    pass


@admin.register(models.InjuryType)
class InjuryTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FireStatus)
class FireStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FireCause)
class FireCauseAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Direction)
class DirectionAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Crops)
class CropsAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TypeOfIllegalActivity)
class TypeOfIllegalActivityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SnareAge)
class SnareAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SnareStatus)
class SnareStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(models.PoacherCampAge)
class PoacherCampAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TypeOfShots)
class TypeOfShotsAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TypeOfTrophy)
class TypeOfTrophyAdmin(admin.ModelAdmin):
    pass


@admin.register(models.VehicleTypes)
class VehicleTypesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.IncidentStatus)
class IncidentStatusAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.WeaponTypes)
class WeaponTypesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TrafficType)
class TrafficTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TrafficActivity)
class TrafficActivityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AccidentType)
class AccidentTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CriticalSightingType)
class CriticalSightingTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TracksType)
class TracksTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.VehicleType)
class VehicleTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.MedicalEquipmentRequired)
class MedicalEquipmentRequiredAdmin(admin.ModelAdmin):
    pass


@admin.register(models.MedicalEvacSecurity)
class MedicalEvacSecurityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.DetectionType)
class DetectionTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Nationality)
class NationalityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Village)
class VillageAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ArrestViolation)
class ArrestViolationAdmin(admin.ModelAdmin):
    pass

# Liwonde specific choices tables


@admin.register(models.AnimalCondition)
class AnimalConditionAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ArrestNationality)
class ArrestNationalityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ReasonForArrest)
class ReasonForArrestAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ArrestVillageName)
class ArrestVillageNameAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpoorAge)
class SpoorAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpoorFootType)
class SpoorFootTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SnareAction)
class SnareActionAdmin(admin.ModelAdmin):
    pass
