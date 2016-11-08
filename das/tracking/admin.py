from django.contrib.gis import admin
import tracking.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static

# class EventAttachmentInline(admin.StackedInline):
#     model=models.EventAttachment

@admin.register(models.SourcePlugin)
class SourcePluginAdmin(admin.ModelAdmin):
    list_display = ['plugin_type', 'source']
    search_fields = ['source__manufacturer_id',]

@admin.register(models.SavannahPlugin)
class SavannahPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.InreachPlugin)
class InreachPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.DemoSourcePlugin)
class DemoPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.AWTHttpPlugin)
class AWTHttpAdmin(admin.ModelAdmin):
    pass

@admin.register(models.InreachKMLPlugin)
class InreachKMLAdmin(admin.ModelAdmin):
    pass

@admin.register(models.SkygisticsSatellitePlugin)
class SkygisticsSatelliteAdmin(admin.ModelAdmin):
    pass

@admin.register(models.FirmsPlugin)
class FirmsPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.SpiderTracksPlugin)
class SpiderTracksPluginAdmin(admin.ModelAdmin):
    pass

@admin.register(models.AWETelemetryPlugin)
class AWETelemetryAdmin(admin.ModelAdmin):
    pass




