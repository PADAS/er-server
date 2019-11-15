import logging
from django.utils import translation
from django.contrib.gis import admin
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.contrib.gis.admin.widgets import OpenLayersWidget

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
    map_template = 'admin/openlayer/ol.html'
    openlayers_url = static('openlayers/v6/ol.js')
    map_srid = 4326
    display_wkt = True
    num_zoom = 19
    units = 'degrees'

    widget = OlWidget
