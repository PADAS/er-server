from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
import mapping.models as models
from mapping.forms import MapCenterForm

# Register your models here.


@admin.register(models.Map)
class MapAdmin(admin.OSMGeoAdmin):
    form = MapCenterForm


@admin.register(models.TileLayer)
class TileLayerAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FeatureSet)
class FeatureSetAdmin(admin.ModelAdmin):
    filter_horizontal = ('types',)


class BaseFeatureAdmin(admin.OSMGeoAdmin):
    wms_layer = 'terrain,overlay'
    wms_url = 'http://tiles.maps.eox.at/wms/'
    list_filter = ('type', 'featureset')
    list_display = ('name', 'type', 'featureset')
    search_fields = ('name', )


@admin.register(models.PolygonFeature)
class PolygonFeatureAdmin(BaseFeatureAdmin):
    pass


@admin.register(models.LineFeature)
class LineFeatureAdmin(BaseFeatureAdmin):
    pass


@admin.register(models.PointFeature)
class PointFeatureAdmin(BaseFeatureAdmin):
    pass


@admin.register(models.FeatureType)
class FeatureTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpatialFeatureGroup)
class SpatialFeatureGroupAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class FeaturesInline(admin.TabularInline):
    model = models.SpatialFeatureGroupStatic.features.through


@admin.register(models.SpatialFeatureGroupStatic)
class SpatialFeatureGroupStaticAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    raw_id_fields = ('features',)


@admin.register(models.SpatialFeatureType)
class SpatialFeatureTypeAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(models.DisplayCategory)
class DisplayCategegoryAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpatialFeature)
class SpatialFeatureAdmin(BaseFeatureAdmin):
    list_display = ('name', 'feature_type', 'external_source')
    list_filter = ('feature_type',)
    search_fields = ('name', 'short_name', 'external_id',)
    inlines = (
        FeaturesInline,
    )


@admin.register(models.SpatialFile)
class SpatialFileAdmin(admin.ModelAdmin):
    pass
