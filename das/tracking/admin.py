import sys, inspect

from django.contrib.gis import admin
import tracking.models as models
import observations.models
from tracking.forms import SourcePluginForm
from django.utils.translation import ugettext_lazy as _


def _get_plugin_class_search_fields():
    '''
    Get a list of search fields to support searching for a SourcePlugin record by the name of the plugin its
    associated with.
    :return: a list of search fields.
    '''
    plugin_classes = inspect.getmembers(sys.modules['tracking.models'], inspect.isclass)

    # Identify the actual plugin classes by those having a 'fetch' function.
    search_names = [f'{n.lower()}__name' for n, c in plugin_classes if n.endswith('Plugin') and hasattr(c, 'fetch')]
    print(f'Search names: {search_names}')
    return search_names


@admin.register(models.SourcePlugin)
class SourcePluginAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.prefetch_related('plugin')
        return queryset

    list_display = ['_source_manufacturer_id', '_source_provider', 'status', '_plugin_name',]
    search_fields = ['source__manufacturer_id'] + _get_plugin_class_search_fields()
    list_select_related = True

    list_filter = ['plugin_type']
    form = SourcePluginForm

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('source', 'status',))
        }
        ),
        ('Plugin', {
            'classes': ('wide',),
            'fields': (('plugin_choice',))
        }
        ),
        ('Advanced Subject Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('cursor_data',)
        })
    )

    def _source_manufacturer_id(self, o):
        return o.source.manufacturer_id
    _source_manufacturer_id.short_description = _('Source Manufacturer ID')

    def _plugin_name(self, o):
        return o.plugin.name
    _plugin_name.short_description = _('Plugin Configuration')

    def _source_provider(self, o):
        return o.source.provider.display_name
    _source_provider.short_description = _('Source Provider')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'source':
            kwargs['queryset'] = observations.models.Source.objects.all().order_by('manufacturer_id').select_related('provider')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
