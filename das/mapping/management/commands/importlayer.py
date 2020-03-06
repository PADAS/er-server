import datetime
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from mapping import models
from mapping.utils import (DEFAULT_SOURCE_NAME, get_datasource_and_layer_num,
                           mappingv2_save_spatial_data, save_spatial_file,
                           validate_feature_record, make_external_id, contains_unique_keys_in_layer)
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
    SUB_COMMANDS = ('importspatialfile', 'importlayerfile', 'importfromesri')

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

        # options for importfromesri
        self.featuretype_label = options['typelabel']
        self.presentation = options['presentation']
        self.arcgis_item_id = options['arcgisitemid']

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
        parser.add_argument('--typelabel', type=str,
                            help='Feature type label on wfs')
        parser.add_argument('--presentation', type=dict,
                            help='Presentation from an ArcGIS Simple Renderer')
        parser.add_argument('--arcgisitemid', type=str,
                            help='Id of the models.ArcgisItem object')

    def importlayerfile(self):

        if not self.featureset and not self.featuretype:
            logger.info('Featureset and featuretype not included in command, add flags --featureset and --featuretype')
            return

        featureset = validate_feature_record(self.featureset, 'Featureset', models.FeatureSet)
        featuretype = validate_feature_record(self.featuretype, 'Featuretype', models.FeatureType)
        logger.debug('Featureset: %s, FeatureType: %s', featureset.name, featuretype.name)

        try:
            datasource, layer_num = get_datasource_and_layer_num(self.filename, self.layer, self.tmpdirs)
            self.import_layer(datasource[layer_num], featuretype, featureset)
        finally:
            datasource = None

    def importspatialfile(self):
        logger.info('Importing features from shapefile: %s',
                    self.filename)
        try:
            datasource, layer_num = get_datasource_and_layer_num(self.filename, self.layer, self.tmpdirs)
            self.import_layer(datasource[layer_num], self.featuretype)
        finally:
            datasource = None

    def get_feature_class(self, name):
        name_lower = name.lower()
        if 'polygon' in name_lower:
            return models.PolygonFeature
        if 'linestring' in name_lower:
            return models.LineFeature
        if 'point' in name_lower:
            return models.PointFeature
        raise KeyError('DAS Feature class not found for {0}'.format(name))

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

    def import_layer(self, layer, featuretype=None, featureset=None):
        logger.info('Importing layer: %s, type: %s, fields: %s',
                    layer.name, layer.geom_type, layer.fields)

        has_unique_keys = contains_unique_keys_in_layer(self.id_field, self.name_field, layer)

        for i, feature in enumerate(layer):
            external_id = make_external_id(self.id_field, self.name_field, layer, feature)
            if not has_unique_keys:
                external_id = external_id + '-' + str(i)
            if featureset:
                self.mappingv1_save_spatial_data(feature, featureset, featuretype, external_id)
            else:
                mappingv2_save_spatial_data(feature, self.source_name, self.spatialfile_id, external_id)

    def mappingv1_save_spatial_data(self, feature, featureset, featuretype, external_id):
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
        save_spatial_file(self.spatialfile_id, models.SpatialFile, feature_record)
        feature_record.save()
