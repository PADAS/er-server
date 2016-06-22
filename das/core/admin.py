from django.contrib import admin
from treebeard.admin import TreeAdmin
# Register your models here.
from core.models import Choice


class HierarchyModelAdmin(TreeAdmin):
    pass


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    pass


