import logging

from django.contrib.gis.utils import layermapping
from django.contrib.gis.gdal import (
    CoordTransform, DataSource, GDALException, OGRGeometry, OGRGeomType,
    SpatialReference,
)
from django.contrib.gis.db.models import MultiLineStringField, MultiPointField, MultiPolygonField


logger = logging.getLogger(__name__)


OGR_MAPPING = {'Polygon': MultiPolygonField,
               'MultiPolygon': MultiPolygonField,
               'Point': MultiPointField,
               'MultiPoint': MultiPointField,
               'LineString': MultiLineStringField,
               'MultiString': MultiLineStringField}


class GeometryMapper(object):
    """Helper for mapping a shapefile geometry to one our db understands. see layermapping.py"""

    def get_db_geom(self, geom, model_field):
        return self.verify_geom(geom, model_field)

    def verify_geom(self, geom, model_field):
        """
        FROM layermapping.py

        Verifies the geometry -- will construct and return a GeometryCollection
        if necessary (for example if the model field is MultiPolygonField while
        the mapped shapefile only contains Polygons).
        """
        coord_dim = model_field.dim
        # Downgrade a 3D geom to a 2D one, if necessary.
        if coord_dim != geom.coord_dim:
            geom.coord_dim = coord_dim

        if self.make_multi(geom.geom_type, model_field):
            # Constructing a multi-geometry type to contain the single geometry
            multi_type = layermapping.LayerMapping.MULTI_TYPES[
                geom.geom_type.num]
            g = OGRGeometry(multi_type)
            g.add(geom)
        else:
            g = geom

        # Transforming the geometry with our Coordinate Transformation object,
        # but only if the class variable `transform` is set w/a CoordTransform
        # object.
        if False:  # self.transform:
            g.transform(self.transform)

        # Returning the WKT of the geometry.
        return g.wkt

    def make_multi(self, geom_type, model_field):
        """
        Given the OGRGeomType for a geometry and its associated GeometryField,
        determine whether the geometry should be turned into a GeometryCollection.
        """
        return (geom_type.num in layermapping.LayerMapping.MULTI_TYPES and
                model_field.__class__.__name__ == 'Multi%s' % geom_type.django)
