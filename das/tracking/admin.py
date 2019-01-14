from django.contrib.gis import admin
import tracking.models as models

from django.contrib.contenttypes.admin import GenericTabularInline, GenericStackedInline


@admin.register(models.SourcePlugin)
class SourcePluginAdmin(admin.ModelAdmin):
    list_display = ['plugin_type', 'source']
    search_fields = ['source__manufacturer_id', ]

# class SourcePluginGenericInline(GenericStackedInline):
#     model = models.SourcePlugin
#     ct_field = 'plugin_type'
#     ct_fk_field = 'plugin_id'
#
#     def get_extra(self, request, obj=None, **kwargs):
#         if obj:
#             return 0
#         return 1
#
#     fields = ('source',)
#
#


@admin.register(models.SavannahPlugin)
class SavannahPluginAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_username', 'service_api_host',)


@admin.register(models.InreachPlugin)
class InreachPluginAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_username', 'service_api_host',)


@admin.register(models.DemoSourcePlugin)
class DemoPluginAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AWTHttpPlugin)
class AWTHttpAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_api_url',)


@admin.register(models.InreachKMLPlugin)
class InreachKMLAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_username', 'service_share_path',)


@admin.register(models.SkygisticsSatellitePlugin)
class SkygisticsSatelliteAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_api_url', 'service_username',)


@admin.register(models.FirmsPlugin)
class FirmsPluginAdmin(admin.ModelAdmin):
    list_display = ('name', 'app_key', 'spatial_feature_group')


@admin.register(models.SpiderTracksPlugin)
class SpiderTracksPluginAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_username', 'service_api',)


@admin.register(models.AWETelemetryPlugin)
class AWETelemetryAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_username', 'service_url',)


@admin.register(models.SirtrackPlugin)
class SirtrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_username', 'service_api',)


@admin.register(models.VectronicsPlugin)
class VectronicsAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(models.AwtPlugin)
class AwtAdmin(admin.ModelAdmin):
    list_display = ('name', 'username', 'host')
