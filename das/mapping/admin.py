import logging
from django.utils import translation
from django.contrib.gis.admin.widgets import OpenLayersWidget
from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.contrib import admin as django_admin
from django.forms import ModelForm, forms
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.utils.html import escape

import mapping.models as models
from mapping.forms import MapCenterForm, TileLayerFormWithAttributes, \
    SpatialFeatureGroupStaticForm
from django.contrib.gis.admin.widgets import OpenLayersWidget


@admin.register(models.Map)
class MapAdmin(admin.OSMGeoAdmin):
    form = MapCenterForm


geo_context = {'LANGUAGE_BIDI': translation.get_language_bidi()}
logger = logging.getLogger('django.contrib.gis')

class OlWidget(OpenLayersWidget):
    """
    Render an OpenLayers map using the WKT of the geometry.
    """
    def map_options(self):
        """Build the map options hash for the OpenLayers template."""

        # JavaScript construction utilities for the Bounds and Projection.
        def ol_bounds(extent):
            return 'new ol.extent.boundingExtent(%s)' % extent

        def ol_projection(srid, units):
            return 'new ol.View({"projection": "EPSG:%s"})' % srid

        # An array of the parameter name, the name of their OpenLayers
        # counterpart, and the type of variable they are.
        map_types = [
            ('srid', 'projection', 'srid'),
            ('display_srid', 'displayProjection', 'srid'),
            ('units', 'units', str),
            ('max_resolution', 'maxResolution', float),
            ('max_extent', 'maxExtent', 'bounds'),
            ('num_zoom', 'numZoomLevels', int),
            ('max_zoom', 'maxZoomLevels', int),
            ('min_zoom', 'minZoomLevel', int),
        ]

        # Building the map options hash.
        map_options = {}
        for param_name, js_name, option_type in map_types:
            if self.params.get(param_name, False):
                if option_type == 'srid':
                    value = ol_projection(self.params[param_name],
                                          self.params['units'])
                elif option_type == 'bounds':
                    value = ol_bounds(self.params[param_name])
                elif option_type in (float, int):
                    value = self.params[param_name]
                elif option_type in (str, ):
                    value = '"%s"' % self.params[param_name]
                else:
                    raise TypeError
                map_options[js_name] = value
        return map_options


class OSMGeoExtendedAdmin(admin.OSMGeoAdmin):
    wms_layer = 'terrain,overlay'
    wms_url = 'http://tiles.maps.eox.at/wms/'
    map_template = 'admin/ol.html'
    openlayers_url = 'https://cdn.jsdelivr.net/gh/openlayers/openlayers.github.io@master/en/v6.0.1/build/ol.js'
    map_srid = 4326
    display_wkt = True
    num_zoom = 19
    units = 'degrees'

    widget = OlWidget

@admin.register(models.Map)
class MapAdmin(OSMGeoExtendedAdmin):
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


class BaseFeatureAdmin(OSMGeoExtendedAdmin):
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
    ordering = ('name', )
    list_display = ('name', )


@admin.register(models.SpatialFeatureGroup)
class SpatialFeatureGroupAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class FeaturesInline(admin.TabularInline):
    model = models.SpatialFeatureGroupStatic.features.through
    form = SpatialFeatureGroupStaticForm
    model._meta.verbose_name_plural = "Member of spatial feature groups"
    extra = 1
    verbose_name = "Spatial Feature Group Static"


@admin.register(models.SpatialFeatureGroupStatic)
class SpatialFeatureGroupStaticAdmin(admin.ModelAdmin):
    ordering = ('name',)
    search_fields = ('name',)
    autocomplete_fields = ('features',)


@admin.register(models.SpatialFeatureType)
class SpatialFeatureTypeAdmin(admin.ModelAdmin):
    ordering = ('name', )
    search_fields = ('name',)


# @admin.register(models.DisplayCategory)
# class DisplayCategegoryAdmin(admin.ModelAdmin):
#     ordering = ('name',)


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
