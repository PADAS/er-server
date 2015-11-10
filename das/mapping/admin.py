from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
import mapping.models as models

# Register your models here.


@admin.register(models.Map)
class MapAdmin(admin.OSMGeoAdmin):
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')


@admin.register(models.TileLayer)
class TileLayerAdmin(admin.ModelAdmin):
    pass

