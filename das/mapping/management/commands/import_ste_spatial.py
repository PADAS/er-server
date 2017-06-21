## import geojson file (geofences) to dev db
import logging
from zipfile import ZipFile
import tempfile
import datetime
import os

from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.utils import LayerMapping
from django.contrib.gis.geos import MultiPolygon, MultiPoint, MultiLineString
from django.contrib.gis.gdal import (
    CoordTransform, DataSource, GDALException, OGRGeometry, OGRGeomType,
    SpatialReference,
)
# from openpyxl import load_workbook #needed for XLS


from mapping import models


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []

    name_field = 'Name'
    id_field = 'globalid'
    utm = None

    def handle(self, *args, **options):

        spatial_mapping = options['spatial_mapping']
        if not spatial_mapping:
            spatial_mapping = 'STESpatial_DataModel.xlsx'

        # if not os.path.exists(spatial_mapping):
        #     raise FileNotFoundError(
        #         'Spatial mapping file not found {0}'.format(spatial_mapping))

        # spatial_mapping = self.load_mapping(spatial_mapping)

        data_source = self.datasource_from_file(options['filename']) #geojson input

        try:
            self.import_layer(data_source, spatial_mapping)
        finally:
            data_source = None

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str,
                            help='spatial filename')
        parser.add_argument('--spatial-mapping', type=str,
                            help='spreadsheet with ste to das display class mapping')

    def load_mapping(self, mapping_file):

        wb = load_workbook(mapping_file, read_only=True)
        ws = next(
            iter([w for w in wb.worksheets if w.title == 'SpatialFeature']))
        row_iter = ws.rows
        first_row = next(row_iter)
        for row in row_iter:
            self.logger.debug('%s', row)

    def datasource_from_file(self, filename):                   # geojson file
        if filename.endswith('kmz'):
            tmpdir = tempfile.TemporaryDirectory()
            self.tmpdirs.append(tmpdir)
            zip = ZipFile(filename)
            filename = zip.extract('doc.kml', tmpdir.name)      #use break
        return DataSource(filename)

    def get_feature_class(self, name):
        name_lower = name.lower()
        if 'polygon' in name_lower:
            return models.PolygonFeature
        if 'linestring' in name_lower:
            return models.LineFeature
        if 'point' in name_lower:
            return models.PointFeature
        raise KeyError('DAS Feature class not found for {0}'.format(name))

    def make_external_id(self, layer, feature):
        external_id = '-'.join((layer.name, feature[self.name_field].value))
        for name in feature.fields:
            name = name.decode('utf8')
            if self.id_field and name == self.id_field:
                external_id += '-' + str(feature[name].value)
        return external_id

    def import_layer(self, datasource, spatial_mapping):
        for feature in datasource[0]:

            print(feature.fields)
            # print(feature.geom_type)
            # print(len(feature))
            # print(feature.num_fields)
            logger.info('%s', feature)
            # mapping = {'title': 'Name'}
            # lm = LayerMapping(SpatialFeature, datasource, mapping)
            # lm.save(verbose=True)


    def make_multi(self, geom_type, model_field):
        """
        Given the OGRGeomType for a geometry and its associated GeometryField,
        determine whether the geometry should be turned into a GeometryCollection.
        """
        return (geom_type.num in layermapping.LayerMapping.MULTI_TYPES and
                model_field.__class__.__name__ == 'Multi%s' % geom_type.django)

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
            multi_type = layermapping.LayerMapping.MULTI_TYPES[geom.geom_type.num]
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
