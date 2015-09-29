from django.contrib import admin
import data_input.models as models



@admin.register(models.PluginConf)
class PluginConfAdmin(admin.ModelAdmin):
    list_display = ['id', 'plugin_name', 'created_at', 'updated_at', 'configuration']

    fields = ['id', 'plugin_name', 'configuration']

@admin.register(models.PluginConfSource)
class PluginConfSourceAdmin(admin.ModelAdmin):
    list_display = ['plugin_conf__name', 'source__manufacturer_id', 'additional']

    def source__manufacturer_id(self, o):
        return o.source.manufacturer_id

    def plugin_conf__name(self, o):
        return o.plugin_conf.plugin_name





