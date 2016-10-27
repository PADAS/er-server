from django.contrib import admin
from choices.models import Choice, DynamicChoice, Conservancy, Behavior, Station, Color, Health, Species, CauseOfDeath, FenceSection, ActionTaken, SectionArea, Team, PoachingMean, Tribe, IllegalActivity, Livestock, ContactType, TrophyStatus, WildlifeGap


class BaseChoiceAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    list_fields = ('name', 'ordernum')
    list_editable = ('name',)


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    pass


@admin.register(DynamicChoice)
class DynamicChoiceAdmin(admin.ModelAdmin):
    pass


@admin.register(Conservancy)
class ConservancyAdmin(BaseChoiceAdmin):
    pass

@admin.register(Behavior)
class BehaviorAdmin(BaseChoiceAdmin):
    pass

@admin.register(Station)
class StationAdmin(BaseChoiceAdmin):
    pass

@admin.register(Color)
class ColorAdmin(BaseChoiceAdmin):
    pass

@admin.register(Health)
class HealthAdmin(BaseChoiceAdmin):
    pass

@admin.register(Species)
class SpeciesAdmin(BaseChoiceAdmin):
    pass

@admin.register(CauseOfDeath)
class CauseOfDeathAdmin(BaseChoiceAdmin):
    pass

@admin.register(FenceSection)
class FenceSectionAdmin(BaseChoiceAdmin):
    pass

@admin.register(ActionTaken)
class ActionTakenAdmin(BaseChoiceAdmin):
    pass

@admin.register(SectionArea)
class SectionAreaAdmin(BaseChoiceAdmin):
    pass

@admin.register(Team)
class TeamAdmin(BaseChoiceAdmin):
    pass

@admin.register(PoachingMean)
class PoachingMeanAdmin(BaseChoiceAdmin):
    pass

@admin.register(Tribe)
class TribeAdmin(BaseChoiceAdmin):
    pass

@admin.register(IllegalActivity)
class IllegalActivityAdmin(BaseChoiceAdmin):
    pass

@admin.register(Livestock)
class LivestockAdmin(BaseChoiceAdmin):
    pass

@admin.register(ContactType)
class ContactTypeAdmin(BaseChoiceAdmin):
    pass

@admin.register(TrophyStatus)
class TrophyStatusAdmin(BaseChoiceAdmin):
    pass

@admin.register(WildlifeGap)
class WildlifeGapAdmin(BaseChoiceAdmin):
    pass







