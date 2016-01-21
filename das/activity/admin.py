from django.contrib import admin
from django.contrib.gis.admin.options import GeoModelAdmin
import activity.models as models


class EventAttachmentInline(admin.StackedInline):
    model=models.EventAttachment

@admin.register(models.Event)
class EventAdmin(GeoModelAdmin):
    # Relying on static content in mapping app.
    openlayers_url = '/static/js/openlayers_2.13/OpenLayers.js'
    list_display = ('created_at', 'event_type', 'name', 'location', 'attributes',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [
        EventAttachmentInline,
    ]


    # list_display = ['id', 'plugin_class', 'plugin_name', 'created_at', 'updated_at', 'configuration']

@admin.register(models.EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    pass



