from django.contrib.gis import admin
import activity.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static

class EventAttachmentInline(admin.StackedInline):
    model=models.EventAttachment

@admin.register(models.Event)
class EventAdmin(admin.OSMGeoAdmin):
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')
    wms_layer = 'terrain,overlay'
    wms_url= 'http://tiles.maps.eox.at/wms/'

    list_display = ('created_at', 'event_type', 'message', 'location', 'attributes',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [
        EventAttachmentInline,
    ]


    # list_display = ['id', 'plugin_class', 'plugin_name', 'created_at', 'updated_at', 'configuration']

@admin.register(models.EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    pass
