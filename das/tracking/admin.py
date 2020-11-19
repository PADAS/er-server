import inspect
import sys

import django
from django.apps import apps
from django.contrib.gis import admin
from django.utils.translation import ugettext_lazy as _

import observations.models
import tracking.models as models
from tracking.forms import SourcePluginForm
from django.forms import CheckboxSelectMultiple


def _get_plugin_class_search_fields():
    '''
    Get a list of search fields to support searching for a SourcePlugin record by the name of the plugin its
    associated with.
    :return: a list of search fields.
    '''
    plugin_classes = inspect.getmembers(sys.modules['tracking.models'], inspect.isclass)

    # Identify the actual plugin classes by having a valid 'source_plugin_reverse_relation' attribute.
    search_names = [f'{c.source_plugin_reverse_relation}__name'
                    for n, c in plugin_classes if getattr(c, 'source_plugin_reverse_relation', None)]
    return search_names

class PluginTypeFilter(django.contrib.admin.SimpleListFilter):
    title = 'Plugin type'
    parameter_name = 'plugin_type'

    def lookups(self, request, model_admin):

        tracking_models = [
            (model.__name__.lower(), model._meta.verbose_name.title())
            for model in apps.get_app_config('tracking').get_models()
            if model.__name__.lower() != 'sourceplugin'
        ]
        return sorted(tracking_models, key=lambda m: m[1])

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(plugin_type__model__iexact=value)
        return queryset

@admin.register(models.SourcePlugin)
class SourcePluginAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.prefetch_related('plugin')
        return queryset

    list_display = ['_source_manufacturer_id', '_source_provider', 'status', '_plugin_name',]
    search_fields = ['source__manufacturer_id'] + _get_plugin_class_search_fields()
    list_select_related = True

    list_filter = [PluginTypeFilter]
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


@admin.register(models.TrackConfiguration)
class TrackConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'new_device_config', 'name_change_config')
    formfield_overrides = {
        django.db.models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }
    fieldsets = (
        ('New device subject handling', {
            'classes': ('wide',),
            'fields': ('new_device_config',)
        }
         ),
        (None, {
            'classes': ('new_subject_types',),
            'fields': ('new_subject_excluded_subject_types',)
        }
         ),
        ('Device name change handling', {
            'classes': ('wide',),
            'fields': ('name_change_config',)
        }
         ),
        (None, {
            'classes': ('name_change_types',),
            'fields': ('name_change_excluded_subject_types',)
        }
         ),
    )

    class Media:
        js = ['admin/js/toggle_subject_types.js',]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super(TrackConfigurationAdmin, self).get_form(request, obj, change, **kwargs)
        form.base_fields['new_subject_excluded_subject_types'].widget.can_add_related = False
        form.base_fields['name_change_excluded_subject_types'].widget.can_add_related = False
        return form
