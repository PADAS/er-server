from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
import mapping.models as models
from mapping.forms import MapCenterForm

# Register your models here.


@admin.register(models.Map)
class MapAdmin(admin.OSMGeoAdmin):
    form = MapCenterForm
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')


@admin.register(models.TileLayer)
class TileLayerAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FeatureSet)
class FeatureSetAdmin(admin.ModelAdmin):
    filter_horizontal = ('types',)


class BaseFeatureAdmin(admin.OSMGeoAdmin):
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')
    wms_layer = 'terrain,overlay'
    wms_url = 'http://tiles.maps.eox.at/wms/'


@admin.register(models.PolygonFeature)
class PolygonFeatureAdmin(BaseFeatureAdmin):
    pass


@admin.register(models.LineFeature)
class LineFeatureAdmin(admin.OSMGeoAdmin):
    pass


@admin.register(models.PointFeature)
class PointFeatureAdmin(admin.OSMGeoAdmin):
    pass


@admin.register(models.FeatureType)
class FeatureTypeAdmin(admin.ModelAdmin):
    pass
