# import geojson file (geofences) to dev db
import logging
from zipfile import ZipFile
import tempfile
import datetime
import os

from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.utils import layermapping
from django.contrib.gis.geos import MultiPolygon, MultiPoint, MultiLineString
from django.contrib.gis.gdal import (
    CoordTransform, DataSource, GDALException, OGRGeometry, OGRGeomType,
    SpatialReference,
)
# from openpyxl import load_workbook #needed for XLS


from mapping import models
# from models import SpatialFeature   #added to import SpatialFeature class


logger = logging.getLogger(__name__)

ATTRIBUTE_FIELDS = ('',)
PROVENANCE_FIELDS = ('collect_user', 'collect_method', 'collect_date',
                     'ground_verified', 'spatial_feature_owners', 'spatial_data_owners',
                     'created_user', 'created_date', 'last_edited_user', 'last_edited_date',
                     'other_id')

STE_TO_SPATIAL_MAPPING = {'short_name': 'short_name',
                          'name': 'name'}


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []

    name_field = 'Name'
    id_field = 'globalid'
    utm = None

    def handle(self, *args, **options):

        # geojson input
        data_source = self.datasource_from_file(options['filename'])

        try:
            self.import_layer(data_source)
        finally:
            data_source = None

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str,
                            help='spatial filename')

    def datasource_from_file(self, filename):                   # geojson file
        if filename.endswith('kmz'):
            tmpdir = tempfile.TemporaryDirectory()
            self.tmpdirs.append(tmpdir)
            zip = ZipFile(filename)
            filename = zip.extract('doc.kml', tmpdir.name)  # use break
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

    def import_layer(self, datasource):
        for feature in datasource[0]:
            logger.debug('Feature fields: %s', str(feature.fields))
            logger.debug('Feature geom type: %s', str(feature.geom_type))
            logger.debug('Feature length: %s', str(len(feature)))
            logger.debug('Feature num of fields: %s', str(feature.num_fields))
            self._save_feature_to_table(feature)

    def _save_feature_to_table(self, feature):
        global_id = feature['globalid'].value
        das_type = feature['das_type'].value
        das_tags = feature['das_tags'].value

        feature_model = models.SpatialFeature
        feature_geometry = feature['']

        attributes = {feature_name: feature[feature_name]
                      for feature_name in feature.fields if
                      feature_name in ATTRIBUTE_FIELDS}

        provenance = {feature_name: feature[feature_name]
                      for feature_name in feature.fields if
                      feature_name in PROVENANCE_FIELDS}

        defaults = {'attributes': attributes, 'provenance': provenance}
        for ste_field, spatial_field in STE_TO_SPATIAL_MAPPING.items():
            if ste_field in feature.fields:
                defaults[spatial_field] = feature.fields[ste_field]

        feature_record, created = feature_model.objects.get_or_create(
            defaults=defaults,
            feature_geometry=feature_geometry,
            external_id=global_id)

        logger.info('Import feature: %s, created:%s',
                    global_id, created)

        feature_record.feature_types = self.get_feature_types(
            self.feature_type_names(None))
        feature_record.display_class = self.get_feature_class(
            self.display_class_names(None))
        if 'das_tags' in feature.fields:
            feature_record.tags = feature.fields['das_tags'].split(',')
        feature_record.feature_geometry = feature_geometry
        for key, value in defaults.items():
            setattr(feature_record, key, value)

        feature_record.save()

    def get_feature_types(self, feature_type_names, create_okay=True):
        pass

    def get_feature_class(self, display_class_names, create_okay=True):
        pass

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
