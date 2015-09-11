from django.contrib import admin
from observations.models import Source, WildlifeSubject

# Register your models here.

@admin.register(WildlifeSubject)
class WildlifeSubjectAdmin(admin.ModelAdmin):
    pass

