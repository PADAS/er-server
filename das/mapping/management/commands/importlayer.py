import logging
from zipfile import ZipFile
import tempfile

from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.utils import layermapping
from django.contrib.gis.geos import MultiPolygon, MultiPoint, MultiLineString
from django.contrib.gis.gdal import (
    CoordTransform, DataSource, GDALException, OGRGeometry, OGRGeomType,
    SpatialReference,
)
from mapping import models

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []

    def handle(self, *args, **options):
        logger.debug('Featureset: %s, FeatureType: %s', options['featureset'], options['featuretype'])
        featureset = models.FeatureSet.objects.get_by_natural_key(options['featureset'])
        featuretype = models.FeatureType.objects.get_by_natural_key(options['featuretype'])
        datasource = self.datasource_from_file(options['filename'])

        logger.debug('Data Source: %s, layercount %s', datasource.name, datasource.layer_count)

        if datasource.layer_count > 1:
            logger.warn('multiple layers not supported...')
            return

        try:
            self.import_layer(featureset, featuretype, datasource[0])
        finally:
            datasource = None


    def add_arguments(self, parser):
        parser.add_argument('filename', type=str,
                            help='spatial filename')
        parser.add_argument('featureset', type=str,
                            help='FeatureSet')
        parser.add_argument('featuretype', type=str,
                            help='FeatureSet')

    def datasource_from_file(self, filename):
        if filename.endswith('kmz'):
            tmpdir = tempfile.TemporaryDirectory()
            self.tmpdirs.append(tmpdir)
            zip = ZipFile(filename)
            filename = zip.extract('doc.kml', tmpdir.name)
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

    def contains_unique_keys_in_layer(self, layer):
        seen = {}
        for feature in layer:
            external_id = '-'.join((layer.name, feature['Name'].value))
            if external_id in seen:
                logger.info('External_id=%s not unique to layer', external_id)
                return False


    def import_layer(self, featureset, featuretype, layer):
        logger.debug('Importing layer: %s, type: %s, fields: %s', layer.name, layer.geom_type, layer.fields)
        has_unique_keys = self.contains_unique_keys_in_layer(layer)
        i = 0
        for feature in layer:
            i+=1
            external_id = '-'.join((layer.name, feature['Name'].value))
            if not has_unique_keys:
                external_id = external_id + '-' + str(i)
            fields = {}
            for name in feature.fields:
                name = name.decode('utf8')
                if name.lower() in ('name', 'description'):
                    continue
                fields[name] = feature[name].value


            feature_model = self.get_feature_class(feature.geom_type.name)
            model_fieldname = 'feature_geometry'
            model_field = feature_model._meta.get_field(model_fieldname)
            feature_geometry = self.verify_geom(feature.geom, model_field)
            defaults = {'feature_geometry': feature_geometry, 'fields': fields}
            feature_record, created = feature_model.objects.get_or_create(
                defaults=defaults,
                featureset=featureset,
                type=featuretype,
                external_id=external_id)

            logger.debug('Import feature: %s, created:%s', external_id, created)

            feature_record.feature_geometry = feature_geometry
            feature_record.fields = fields
            feature_record.name = feature['Name'].value
            try:
                feature_record.description = feature['Description'].value
            except KeyError:
                pass
            feature_record.save()

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
            multi_type = self.MULTI_TYPES[geom.geom_type.num]
            g = OGRGeometry(multi_type)
            g.add(geom)
        else:
            g = geom

        # Transforming the geometry with our Coordinate Transformation object,
        # but only if the class variable `transform` is set w/a CoordTransform
        # object.
        if False: #self.transform:
            g.transform(self.transform)

        # Returning the WKT of the geometry.
        return g.wkt
