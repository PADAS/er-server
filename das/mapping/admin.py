from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.contrib import admin as django_admin
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.contrib.gis.geos import Point

import mapping.models as models
from mapping.forms import MapCenterForm, TileLayerFormWithAttributes


@admin.register(models.Map)
class MapAdmin(admin.OSMGeoAdmin):
    form = MapCenterForm


@admin.register(models.TileLayer)
class TileLayerAdmin(admin.ModelAdmin):
    ordering = ('ordernum', 'name')
    list_display = ('name', 'ordernum', 'get_attributes')
    list_editable = ('ordernum',)
    form = TileLayerFormWithAttributes
    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('id', 'name',))
        }
        ),
        ('Tile Layer Attributes', {
            'classes': ('wide',),
            'fields': (('type', 'title', 'url', 'icon_url', 'configuration'))
        }
        ),
        ('Advanced Tile Layer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('attributes', 'created_at', 'updated_at',)
        })
    )
    readonly_fields = ('id', 'created_at', 'updated_at',)
    list_per_page = 25

    def get_attributes(self, instance):
        context = dict((k, instance.attributes[k]) for k in (
            'type', 'title', 'url', 'configuration') if k in instance.attributes)

        return mark_safe(''.join('<p><strong>{}</strong>: {}</p>'.format(escape(k), escape(v))
                                 for k, v in context.items()))

    get_attributes.short_description = _('Tile Layer Attributes (TileJSON)')


@admin.register(models.FeatureSet)
class FeatureSetAdmin(admin.ModelAdmin):
    filter_horizontal = ('types',)


class BaseFeatureAdmin(admin.OSMGeoAdmin):
    wms_layer = 'terrain,overlay'
    wms_url = 'http://tiles.maps.eox.at/wms/'
    list_filter = ('type', 'featureset')
    list_display = ('name', 'type', 'featureset')
    search_fields = ('name', )

    map_srid = 4326

    def get_single_coordinate_pair(self, coords):
        try:
            if not isinstance(coords[0], tuple):
                return coords
            return self.get_single_coordinate_pair(coords[0])
        except Exception:
            return (0, 0)
        
    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            # the map in the admin uses EPSG 3857 by default and changing the
            # map_srid here doesn't have any effect on the map.
            # This workaround converts EPSG 4326 coordinates to EPSG 3857 so
            # that the map can be centered to that position
            lon, lat = 0, 0
            try:
                lon = float(request.COOKIES.get('longitude', 0))
                lat = float(request.COOKIES.get('latitude', 0))
            except ValueError:
                pass

            p = Point(lon, lat, srid=4326)
            p.transform(3857)
            self.default_lat = p.y
            self.default_lon = p.x
        return super(BaseFeatureAdmin, self).get_form(request, obj=None, **kwargs)

    def set_coordinates_cookie(self, http_response, obj):
        coords = obj.feature_geometry.coords
        long, lat = self.get_single_coordinate_pair(coords)
        http_response.set_cookie("latitude", lat, max_age=365 * 24 * 60 * 60)
        http_response.set_cookie("longitude", long, max_age=365 * 24 * 60 * 60)
        return http_response

    def response_post_save_add(self, request, obj):
        http_response = super(BaseFeatureAdmin,
                              self).response_post_save_add(request, obj)
        response = self.set_coordinates_cookie(http_response, obj)
        return response

    def response_post_save_change(self, request, obj):
        http_response = super(BaseFeatureAdmin,
                              self).response_post_save_change(request, obj)
        response = self.set_coordinates_cookie(http_response, obj)
        return response


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
    ordering = ('name', )


@admin.register(models.SpatialFeatureGroup)
class SpatialFeatureGroupAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class FeaturesInline(admin.TabularInline):
    model = models.SpatialFeatureGroupStatic.features.through


@admin.register(models.SpatialFeatureGroupStatic)
class SpatialFeatureGroupStaticAdmin(admin.ModelAdmin):
    ordering = ('name',)
    search_fields = ('name',)
    autocomplete_fields = ('features',)


@admin.register(models.SpatialFeatureType)
class SpatialFeatureTypeAdmin(admin.ModelAdmin):
    ordering = ('name', )
    search_fields = ('name',)


@admin.register(models.DisplayCategory)
class DisplayCategegoryAdmin(admin.ModelAdmin):
    ordering = ('name',)


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
    ordering = ('name',)
    list_display = ('name', 'feature_type',
                    'external_source', 'geometry_type',)
    list_filter = (GeometryTypeFilter, 'feature_type',)
    search_fields = ('name', 'short_name', 'external_id', 'id')
    inlines = (
        FeaturesInline,
    )

    def get_queryset(self, request):
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
