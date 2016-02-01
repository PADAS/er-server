from django.contrib.gis import admin
import tracking.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static

# class EventAttachmentInline(admin.StackedInline):
#     model=models.EventAttachment

@admin.register(models.SourcePlugin)
class SourcePluginAdmin(admin.ModelAdmin):
    list_display = ['plugin_type', 'source']

@admin.register(models.SavannahPlugin)
class SavannahPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.InreachPlugin)
class InreachPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.DemoSubjectPlugin)
class DemoPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.AWTHttpPlugin)
class AWTHttpAdmin(admin.ModelAdmin):
    pass




