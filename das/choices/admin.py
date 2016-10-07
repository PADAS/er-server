from django.contrib import admin
from choices.models import Choice, DynamicChoice, Conservancy, Behavior, Station, Color, Health, Species, CauseOfDeath, FenceSection, ActionTaken

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