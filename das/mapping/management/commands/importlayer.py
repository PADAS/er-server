import logging

from django.core.management.base import BaseCommand

from mapping import models
from mapping.tasks import load_spatial_features_from_files
from mapping.utils import DEFAULT_SOURCE_NAME, validate_feature_record

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        self.source_name = options['source'] if options['source'] else DEFAULT_SOURCE_NAME
        self.filename = options['filename']
        self.name_field = options['name_field'] if options['name_field'] else self.default_name_field
        self.id_field = options['id_field'] if options[
            'id_field'] else self.id_field
        self.layer = options['layer']
        self.utm = options['utm'] if options['utm'] else self.utm
        self.featuretype = options['featuretype']
        self.featuretype_label = options['typelabel']
        self.featureset = options['featureset']
        self.spatialfile_id = options['spatialfile_id'] if options['spatialfile_id'] else self.spatialfile_id
        self.presentation = options['presentation']

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
        parser.add_argument('--typelabel', type=str,
                            help='Feature type label on wfs')
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
        parser.add_argument('--presentation', type=dict,
                            help='Presentation from an ArcGIS Simple Renderer')

    def importlayerfile(self):

        if not self.featureset and not self.featuretype:
            logger.info('Featureset and featuretype not included in command, add flags --featureset and --featuretype')
            return

        featureset = validate_feature_record(
            self.featureset, 'Featureset', models.FeatureSet)
        featuretype = validate_feature_record(
            self.featuretype, 'Featuretype', models.FeatureType)
        logger.debug('Featureset: %s, FeatureType: %s',
                     featureset.name, featuretype.name)

        load_spatial_features_from_files.apply_async(args=(
            self.filename, self.tmpdirs, self.source_name, self.spatialfile_id,
            None, self.layer, self.presentation, self.featuretype_label,
            self.id_field, self.name_field, featuretype.name, featureset.name,))

    def importspatialfile(self):
        logger.info('Importing features from shapefile: %s',
                    self.filename)
        featuretype = self.featuretype 
        if featuretype:
            featuretype = featuretype if isinstance(featuretype, str) else featuretype.name
        load_spatial_features_from_files.apply_async(args=(
            self.filename, self.tmpdirs, self.source_name, self.spatialfile_id,
            None, self.layer, self.presentation, self.featuretype_label,
            self.id_field, self.name_field, featuretype,))
