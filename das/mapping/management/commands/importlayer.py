import datetime
import logging

from django.core.management.base import BaseCommand

from mapping import models
from mapping.utils import (DEFAULT_SOURCE_NAME, MAPPING_FEATURES_V2,
                           datasource_from_file, save_feature_to_table,
                           validate_feature_record)
from utils.spatial import GeometryMapper

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
    SUB_COMMANDS = ('importspatialfile', 'importlayerfile')

    default_name_field = 'Name'
    id_field = 'globalid'
    spatialfile_id = None

    # model for feature? could these be combined in to one dictionary attribute?
    # stroke = 'stroke'
    # stroke_width = 'stroke-width'
    # stroke_opacity = 'stroke-opacity'
    utm = None
    geometry_mapper = GeometryMapper()

    def handle(self, *args, **options):
        self.source_name = options['source'] if options['source'] else DEFAULT_SOURCE_NAME
        self.filename = options['filename']
        self.name_field = options['name_field'] if options['name_field'] else self.default_name_field
        self.id_field = options['id_field'] if options[
            'id_field'] else self.id_field
        self.layer = options['layer']
        self.utm = options['utm'] if options['utm'] else self.utm
        self.featuretype = options['featuretype']
        self.featureset = options['featureset']
        self.spatialfile_id = options['spatialfile_id'] if options['spatialfile_id'] else self.spatialfile_id

        sub_command = options['sub_command']
        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))
        getattr(self, sub_command)()

    def add_arguments(self, parser):
        parser.add_argument('sub_command', type=str,
                            help='supported commands are {0}'.format(Command.SUB_COMMANDS))
        parser.add_argument('filename', type=str,
                            help='spatial filename')

        parser.add_argument('--featuretype', type=str,
                            help='Feature type')

        parser.add_argument('--featureset', type=str,
                            help='FeatureSet')
        parser.add_argument(
                '--source', type=str, help=f'Source of data, default is {DEFAULT_SOURCE_NAME}')
        parser.add_argument('--layer', type=int,
                            help='Layer to import')
        parser.add_argument('--name-field', type=str,
                            help='Name Field from the attributes table')
        parser.add_argument('--id-field', type=str,
                            help='ID field for the row')
        parser.add_argument('--utm', type=str,
                            help='Change to this utm')
        parser.add_argument('--spatialfile-id', type=str,
                            help='Spatial file ID')

    def importlayerfile(self):
        if MAPPING_FEATURES_V2:
            raise NotImplementedError(
                f'importlayer management command deprecated, use import_spatial command or importspatialfile subcommand')

        if not self.featureset and not self.featuretype:
            logger.info('Featureset and featuretype not included in command, add flags --featureset and --featuretype')
            return

        featureset = validate_feature_record(self.featureset, 'Featureset', models.FeatureSet)
        featuretype = validate_feature_record(self.featuretype, 'Featuretype', models.FeatureType)
        logger.debug('Featureset: %s, FeatureType: %s', featureset.name, featuretype.name)

        datasource, layer_num = self.get_datasource_and_layer_num()
        try:
            self.import_layer(datasource[layer_num], featuretype, featureset)
        finally:
            datasource = None

    def importspatialfile(self):
        logger.info('Importing features from shapefile: %s',
                    self.filename)
        datasource, layer_num = self.get_datasource_and_layer_num()
        try:
            self.import_layer(datasource[layer_num], self.featuretype)
        finally:
            datasource = None

    def get_datasource_and_layer_num(self):
        datasource = datasource_from_file(self.filename, self.tmpdirs)
        logger.debug('Data Source: %s, layercount %s',
                     datasource.name, datasource.layer_count)
        if datasource.layer_count > 1 and self.layer is None:
            logger.warning('multiple layers not supported...')
            for i in range(0, datasource.layer_count):
                logger.info('layer: %s, name: %s', i, datasource[i].name)
            return

        layer_num = 0 if self.layer is None else self.layer
        if layer_num >= datasource.layer_count:
            logger.warning(f'Given layer {self.layer} should be less than existing layers: {datasource.layer_count}')
            layer_num = 0
        return datasource, layer_num

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
        # TODO: review with Kezzy
        name_value = ''
        id_value = ''
        for name in feature.fields:
            if self.id_field and name == self.id_field:
                id_value = str(feature[name].value)
            elif self.name_field and name == self.name_field:
                name_value = str(feature[name].value)
        return '-'.join((layer.name, name_value, id_value))

    def get_featuretype_for_feature(self, feature, default=None):
        for name in feature.fields:
            if name in ('roadclass',):
                value = feature[name].value
                type_name = FEATURE_TYPES[value]
                featuretype = models.FeatureType.objects.get_by_natural_key(
                    type_name)
                return featuretype

        if not default:
            raise KeyError('no default featuretype specified')
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

    def import_layer(self, layer, featuretype=None, featureset=None):
        logger.info('Importing layer: %s, type: %s, fields: %s',
                    layer.name, layer.geom_type, layer.fields)
        has_unique_keys = self.contains_unique_keys_in_layer(layer)
        i = 0
        for feature in layer:
            i += 1
            external_id = self.make_external_id(layer, feature)
            if not has_unique_keys:
                external_id = external_id + '-' + str(i)
            if featureset:
                self.save_to_layer_model(feature, featureset, featuretype, external_id)
            else:
                save_feature_to_table(feature, self.source_name, featuretype, external_id)

    def save_to_layer_model(self, feature, featureset, featuretype, external_id):
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
            type=self.get_featuretype_for_feature(
                feature, default=featuretype),
            external_id=external_id)

        logger.debug('Import feature: %s, created:%s',
                     external_id, created)

        feature_record.feature_geometry = feature_geometry
        feature_record.fields = fields
        try:
            feature_record.name = feature[self.name_field].value
        except (KeyError, IndexError):
            pass
        try:
            feature_record.description = feature['Description'].value
        except (KeyError, IndexError):
            pass
        if self.spatialfile_id:
            feature_record.spatialfile_id = self.spatialfile_id
        feature_record.save()
