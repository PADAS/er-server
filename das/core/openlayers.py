import logging

from django.contrib.gis import admin
from django.contrib.gis.admin.widgets import OpenLayersWidget
from django.templatetags.static import static
from django.utils import translation

from core.admin import SaveCoordinatesToCookieMixin
from mapping.models import TileLayer

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
            ('default_lon', 'defaultLon', float),
            ('default_lat', 'defaultLat', float),
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


class PropsOSMGeoAdminMixin(admin.OSMGeoAdmin, SaveCoordinatesToCookieMixin):
    wms_layer = 'terrain,overlay'
    wms_url = 'http://tiles.maps.eox.at/wms/'
    map_template = 'admin/openlayer/ol.html'
    openlayers_url = static('openlayers/v6/ol.js')
    map_srid = 4326
    display_wkt = True
    num_zoom = 19
    map_width = 800
    map_height = 600
    units = 'degrees'

    gis_geometry_field_name = 'feature_geometry'

    widget = OlWidget

    def get_map_widget(self, db_field):
        OLMap = super().get_map_widget(db_field)
        OLMap.params['tile_layers'] = list(
            TileLayer.objects.values('attributes'))
        return OLMap


class OSMGeoExtendedAdmin(PropsOSMGeoAdminMixin, SaveCoordinatesToCookieMixin):

    def get_form(self, request, obj=None, change=False, **kwargs):
        if not obj:
            lon, lat = 0, 0
            try:
                lon = float(request.COOKIES.get('longitude', 0))
                lat = float(request.COOKIES.get('latitude', 0))
            except ValueError:
                pass

            self.default_lat = lat
            self.default_lon = lon
        return super().get_form(request, obj=None, **kwargs)

    def response_post_save_add(self, request, obj):
        http_response = super().response_post_save_add(request, obj)
        response = self.set_coordinates_cookie(http_response, obj)
        return response

    def response_post_save_change(self, request, obj):
        http_response = super().response_post_save_change(request, obj)
        response = self.set_coordinates_cookie(http_response, obj)
        return response

    def response_change(self, request, obj):
        if "_addanother" in request.POST:
            http_response = super().response_change(request, obj)
            response = self.set_coordinates_cookie(http_response, obj)
            return response
        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        if "_addanother" in request.POST:
            http_response = super().response_add(
                request, obj, post_url_continue)
            response = self.set_coordinates_cookie(http_response, obj)
            return response
        return super().response_add(request, obj, post_url_continue)
