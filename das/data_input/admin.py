from django.contrib import admin
import data_input.models as models



@admin.register(models.PluginConf)
class PluginConfAdmin(admin.ModelAdmin):
    pass


@admin.register(models.PluginConfSource)
class PluginConfSourceAdmin(admin.ModelAdmin):
    pass





