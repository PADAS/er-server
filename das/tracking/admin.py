import inspect
import logging
import sys
from functools import partial

import django
from django.apps import apps
from django.contrib import messages
from django.contrib.gis import admin
from django.db import transaction
from django.db.utils import IntegrityError
from django.forms import CheckboxSelectMultiple, modelformset_factory
from django.http.response import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

import observations.models
import tracking.models as models
from observations.admin import ModelFormSet
from tracking.forms import SourcePluginForm

logger = logging.getLogger(__name__)


def _get_plugin_class_search_fields():
    '''
    Get a list of search fields to support searching for a SourcePlugin record by the name of the plugin its
    associated with.
    :return: a list of search fields.
    '''
    plugin_classes = inspect.getmembers(
        sys.modules['tracking.models'], inspect.isclass)

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

    list_display = ['_source_manufacturer_id',
                    '_source_provider', 'status', '_plugin_name', ]
    search_fields = ['source__manufacturer_id'] + \
        _get_plugin_class_search_fields()
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
            kwargs['queryset'] = observations.models.Source.objects.all().order_by(
                'manufacturer_id').select_related('provider')
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


@admin.register(models.SourceProviderConfiguration)
class SourceProviderConfigurationAdmin(admin.ModelAdmin):

    list_display = ('friendly_name', 'new_device_config',
                    'name_change_config', 'is_default',)
    list_editable = ('is_default',)

    formfield_overrides = {
        django.db.models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }
    fieldsets = (
        ('New device subject handling', {
            'fields': (('new_device_config', 'new_device_match_case'),)
        }
        ),
        (None, {
            'classes': ('new_subject_types',),
            'fields': ('new_subject_excluded_subject_types',)
        }
        ),
        ('Device name change handling', {
            'fields': (('name_change_config', 'name_change_match_case'),)
        }
        ),
        (None, {
            'classes': ('name_change_types',),
            'fields': ('name_change_excluded_subject_types',)
        }
        ),
    )

    def has_add_permission(self, request, obj=None):
        if self.model.objects.count():
            return False
        return super().has_add_permission(request)

    def friendly_name(self, instance):
        if instance.source_provider:
            return f'Config for {instance.source_provider.display_name}'
        else:
            return 'Default Configuration' if instance.is_default else 'Unassociated configuration'

    friendly_name.short_description = 'Friendly display name'

    class Media:
        js = ['admin/js/toggle_subject_types.js', ]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super(SourceProviderConfigurationAdmin, self).get_form(
            request, obj, change, **kwargs)
        form.base_fields['new_subject_excluded_subject_types'].widget.can_add_related = False
        form.base_fields['name_change_excluded_subject_types'].widget.can_add_related = False
        return form

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError:
            self.message_user(
                request, "A default configuration already exists. Only one allowed", level=messages.WARNING)
            return HttpResponseRedirect(request.get_full_path())

    @transaction.atomic
    def changelist_view(self, request, extra_context=None):
        url_path = request.get_full_path()
        try:
            response = super(SourceProviderConfigurationAdmin,
                             self).changelist_view(request, extra_context)
            return response
        except IntegrityError:
            msg = _("Warning: A default configuration has already been set.")
            self.message_user(request, msg, level=messages.WARNING)
            return HttpResponseRedirect(url_path)

    def get_changelist_formset(self, request, **kwargs):
        if request.method == 'POST':
            defaults = {
                'formfield_callback': partial(self.formfield_for_dbfield, request=request),
                **kwargs,
            }
            return modelformset_factory(
                self.model, self.get_changelist_form(request), formset=ModelFormSet,  extra=0,
                fields=self.list_editable, **defaults)
        return super(SourceProviderConfigurationAdmin, self).get_changelist_formset(request, **kwargs)
