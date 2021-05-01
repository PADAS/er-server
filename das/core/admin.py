import logging

from django.contrib import admin
# Register your models here.

logger = logging.getLogger('django.contrib.gis')


class HierarchyModelAdmin(admin.ModelAdmin):
    pass


class InlineExtraDynamicMixin:
    '''
    This allows me to override the 'number of extra inline forms' depending on whether the
    containing object already exists.
    Inheriting class should include `extra` if the default is not desired.
    '''
    extra = 1

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return self.extra


class SaveCoordinatesToCookieMixin:
    gis_geometry_field_name = 'location'

    def get_single_coordinate_pair(self, coords):
        try:
            if not isinstance(coords[0], tuple):
                return coords
            return self.get_single_coordinate_pair(coords[0])
        except IndexError as ex:
            logger.exception(f"Get single coordinate pair failed with {ex}")
        return (0, 0)

    def set_coordinates_cookie(self, http_response, obj):
        coords = None
        try:
            geom = getattr(obj, self.gis_geometry_field_name)
            if geom:
                coords = geom.coords
        except AttributeError as ex:
            logger.exception(
                f"Failed to get GIS geometry attribute on this obj {obj}: {ex}")
        else:
            if coords:
                long, lat = self.get_single_coordinate_pair(coords)
                http_response.set_cookie("latitude", lat,
                                         max_age=365 * 24 * 60 * 60)
                http_response.set_cookie("longitude", long,
                                         max_age=365 * 24 * 60 * 60)
        return http_response
