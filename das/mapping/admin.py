from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
import mapping.models as models
from mapping.forms import MapCenterForm

from django.contrib import admin as django_admin
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


from django.db.models.expressions import RawSQL


class GeometryTypeFilter(django_admin.SimpleListFilter):
    title = 'Geometry Type'
    parameter_name = 'geometry_type'

    def lookups(self, request, model_admin):
        return (
            ('MULTILINESTRING', 'Multi-line String'),
            ('MULTIPOLYGON', 'Multi-polygon'),
            ('LINESTRING', 'Line String'),
            ('POLYGON', 'Polygon'),
            ('MULTIPOINT', 'Multi-point'),
            ('POINT', 'Point'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(geometry_type=value)

        return queryset


@admin.register(models.SpatialFeature)
class SpatialFeatureAdmin(BaseFeatureAdmin):
    list_display = ('name', 'feature_type',
                    'external_source', 'geometry_type',)
    list_filter = (GeometryTypeFilter, 'feature_type',)
    search_fields = ('name', 'short_name', 'external_id',)
    inlines = (
        FeaturesInline,
    )

    def get_queryset(self, request):
        """Limit Subjects to those this person can administer"""
        qs = super().get_queryset(request)
        qs = qs.annotate(geometry_type=RawSQL(
            '''geometryType(feature_geometry)''', ()))
        return qs

    def geometry_type(self, obj):
        return obj.geometry_type

    geometry_type.short_description = 'Geometry Type'


@admin.register(models.SpatialFile)
class SpatialFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'feature_set', 'feature_type',
                    'layer_number')
    list_filter = ('feature_set', 'feature_type')
