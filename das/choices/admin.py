from django.contrib import admin
from choices.models import Choice, DynamicChoice, Conservancy, Behavior, Station, Color, Health, Species, CauseOfDeath, FenceSection, ActionTaken, SectionArea, Team, PoachingMean, Tribe, IllegalActivity, Livestock, ContactType, TrophyStatus, WildlifeGap

@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    pass


@admin.register(DynamicChoice)
class DynamicChoiceAdmin(admin.ModelAdmin):
    pass


@admin.register(Conservancy)
class ConservancyAdmin(admin.ModelAdmin):
    pass

@admin.register(Behavior)
class BehaviorAdmin(admin.ModelAdmin):
    pass

@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    pass

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    pass

@admin.register(Health)
class HealthAdmin(admin.ModelAdmin):
    pass

@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    pass

@admin.register(CauseOfDeath)
class CauseOfDeathAdmin(admin.ModelAdmin):
    pass

@admin.register(FenceSection)
class FenceSectionAdmin(admin.ModelAdmin):
    pass

@admin.register(ActionTaken)
class ActionTakenAdmin(admin.ModelAdmin):
    pass

@admin.register(SectionArea)
class SectionAreaAdmin(admin.ModelAdmin):
    pass

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    pass

@admin.register(PoachingMean)
class PoachingMeanAdmin(admin.ModelAdmin):
    pass

@admin.register(Tribe)
class TribeAdmin(admin.ModelAdmin):
    pass

@admin.register(IllegalActivity)
class IllegalActivityAdmin(admin.ModelAdmin):
    pass

@admin.register(Livestock)
class LivestockAdmin(admin.ModelAdmin):
    pass

@admin.register(ContactType)
class ContactTypeAdmin(admin.ModelAdmin):
    pass

@admin.register(TrophyStatus)
class TrophyStatusAdmin(admin.ModelAdmin):
    pass

@admin.register(WildlifeGap)
class WildlifeGapAdmin(admin.ModelAdmin):
    pass







