from django.contrib import admin
# Register your models here.
from core.models import Choice, DynamicChoice


class HierarchyModelAdmin(admin.ModelAdmin):
    pass


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    pass


@admin.register(DynamicChoice)
class DynamicChoiceAdmin(admin.ModelAdmin):
    pass


