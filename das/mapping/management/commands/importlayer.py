import logging
from zipfile import ZipFile
import tempfile
import datetime

from django.core.management.base import BaseCommand
from django.contrib.gis.utils import layermapping
from django.contrib.gis.gdal import (
    CoordTransform, DataSource, GDALException, OGRGeometry, OGRGeomType,
    SpatialReference,
)

from utils.spatial import GeometryMapper
from mapping import models

logger = logging.getLogger(__name__)


FEATURE_TYPES = {
    'Primary': 'Primary Roads',
    'Secondary': 'Secondary Roads',
    'Old': 'Old Roads',
    'Tertiary': 'Tertiary Roads',
}


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []

    name_field = 'Name'
    id_field = 'globalid'

    # model for feature? could these be combined in to one dictionary attribute?
    # stroke = 'stroke'
    # stroke_width = 'stroke-width'
    # stroke_opacity = 'stroke-opacity'
    utm = None
    geometry_mapper = GeometryMapper()

    def handle(self, *args, **options):
        logger.debug('Featureset: %s, FeatureType: %s',
                     options['featureset'], options['featuretype'])
        featureset = models.FeatureSet.objects.get_by_natural_key(
            options['featureset'])
        featuretype = models.FeatureType.objects.get_by_natural_key(
            options['featuretype'])
        datasource = self.datasource_from_file(options['filename'])
        self.name_field = options['name_field'] if options['name_field'] else self.name_field
        self.id_field = options['id_field'] if options[
            'id_field'] else self.id_field
        self.utm = options['utm'] if options['utm'] else self.utm

        logger.debug('Data Source: %s, layercount %s',
                     datasource.name, datasource.layer_count)

        if datasource.layer_count > 1 and options['layer'] is None:
            logger.warn('multiple layers not supported...')
            for i in range(0, datasource.layer_count):
                logger.info('layer: %s, name: %s', i, datasource[i].name)
            return

        layer_num = 0 if options['layer'] is None else options['layer']
        try:
            self.import_layer(featureset, featuretype, datasource[layer_num])
        finally:
            datasource = None

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str,
                            help='spatial filename')
        parser.add_argument('featureset', type=str,
                            help='FeatureSet')
        parser.add_argument('featuretype', type=str,
                            help='FeatureSet')
        parser.add_argument('--layer', type=int,
                            help='Layer to import')
        parser.add_argument('--name-field', type=str,
                            help='Name Field from the attributes table')
        parser.add_argument('--id-field', type=str,
                            help='ID field for the row')
        parser.add_argument('--utm', type=str,
                            help='Change to this utm')

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

    def make_external_id(self, layer, feature):
        external_id = '-'.join((layer.name, feature[self.name_field].value))
        for name in feature.fields:
            if self.id_field and name == self.id_field:
                external_id += '-' + str(feature[name].value)
        return external_id

    def get_feature_type_for_feature(self, feature, default=None):
        for name in feature.fields:
            if name in ('roadclass',):
                value = feature[name].value
                type_name = FEATURE_TYPES[value]
                feature_type = models.FeatureType.objects.get_by_natural_key(
                    type_name)
                return feature_type

        if not default:
            raise KeyError('no default feature_type specified')
        return default

    def contains_unique_keys_in_layer(self, layer):
        seen = set()
        unique_keys = True
        for feature in layer:
            external_id = self.make_external_id(layer, feature)
            if external_id in seen:
                logger.info('External_id=%s not unique to layer', external_id)
                unique_keys = False
            else:
                seen.add(external_id)
        return unique_keys

    def import_layer(self, featureset, featuretype, layer):
        logger.debug('Importing layer: %s, type: %s, fields: %s',
                     layer.name, layer.geom_type, layer.fields)
        has_unique_keys = self.contains_unique_keys_in_layer(layer)
        i = 0
        for feature in layer:
            i += 1
            external_id = self.make_external_id(layer, feature)
            if not feature[self.name_field].value:
                logger.warning('Missing name field %s for this feature: %s',
                               self.name_field, feature)
                continue

            if not has_unique_keys:
                external_id = external_id + '-' + str(i)
            fields = {}
            for name in feature.fields:
                if name.lower() in (self.name_field.lower(), 'description'):
                    continue
                value = feature[name].value
                if isinstance(value, datetime.date):
                    value = value.isoformat()
                fields[name] = value

            try:
                feature_model = self.get_feature_class(feature.geom_type.name)
            except KeyError as ke:
                feature_model = self.get_feature_class(str(feature.geom))

            model_fieldname = 'feature_geometry'
            model_field_type = feature_model._meta.get_field(model_fieldname)
            feature_geometry = self.geometry_mapper.get_db_geom(
                feature.geom, model_field_type)
            defaults = {'feature_geometry': feature_geometry, 'fields': fields}
            feature_record, created = feature_model.objects.get_or_create(
                defaults=defaults,
                featureset=featureset,
                type=self.get_feature_type_for_feature(
                    feature, default=featuretype),
                external_id=external_id)

            logger.debug('Import feature: %s, created:%s',
                         external_id, created)

            feature_record.feature_geometry = feature_geometry
            feature_record.fields = fields
            feature_record.name = feature[self.name_field].value
            try:
                feature_record.description = feature['Description'].value
            except (KeyError, IndexError):
                pass
            feature_record.save()
