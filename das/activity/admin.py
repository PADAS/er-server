from django.contrib import admin
from django.contrib.gis.admin.options import GeoModelAdmin
import activity.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static


class EventAttachmentInline(admin.StackedInline):
    model=models.EventAttachment

@admin.register(models.Event)
class EventAdmin(GeoModelAdmin):
    # Relying on static content in mapping app.
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')
    # wms_layer = 'MODIS_Terra_CorrectedReflectance_TrueColor'
    # wms_url = 'http://map1a.vis.earthdata.nasa.gov/wmts-geo/wmts.cgi'

    wms_layer = 'terrain,overlay'
    wms_url= 'http://tiles.maps.eox.at/wms/'
    list_display = ('created_at', 'event_type', 'name', 'location', 'attributes',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [
        EventAttachmentInline,
    ]


    # list_display = ['id', 'plugin_class', 'plugin_name', 'created_at', 'updated_at', 'configuration']

@admin.register(models.EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    pass



