import logging
import os

from django.core.management.base import BaseCommand

from mapping import models
from mapping.tasks import load_spatial_features_from_files
from mapping.spatialfile_utils import extract_features_from_files
from mapping.utils import DEFAULT_SOURCE_NAME, validate_feature_record, default_name_field, default_id_field, SPATIAL_FILES_FOLDER
from utils.spatial import GeometryMapper
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []
    SUB_COMMANDS = ('importspatialfile', 'importlayerfile')

    # model for feature? could these be combined in to one dictionary attribute?
    # stroke = 'stroke'
    # stroke_width = 'stroke-width'
    # stroke_opacity = 'stroke-opacity'

    def handle(self, *args, **options):
        self.source_name = options['source'] or DEFAULT_SOURCE_NAME
        self.filename = options['filename']
        self.name_field = options['name_field'] or default_name_field
        self.id_field = options['id_field'] or default_id_field
        self.layer = options['layer']
        self.utm = options['utm']
        self.featuretype = options['featuretype']
        self.featureset = options['featureset']
        self.feature_types_file = options['feature_types']
        self.spatialfile_id = options['spatialfile_id']

        sub_command = options['sub_command']
        if sub_command not in self.SUB_COMMANDS:
            raise NameError('Command: {0} not supported'.format(sub_command))

        # validate upload file paths  
        if not self.all_files_exist():
            return 

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
        parser.add_argument('--feature-types',
                            help='spatial feature types file')

    def importlayerfile(self):
        if not self.featureset and not self.featuretype:
            logger.info('Featureset and featuretype not included in command, add flags --featureset and --featuretype')
            return
        
        featureset = validate_feature_record(self.featureset, 'Featureset', models.FeatureSet)
        featuretype = validate_feature_record(self.featuretype, 'Featuretype', models.FeatureType)

        data = {'layer_number': self.layer,
                'name_field': self.name_field, 'id_field': self.id_field,
                'feature_type': featuretype, 'feature_set': featureset}
        self.read_file_and_load_features(models.SpatialFile, data)

    def importspatialfile(self):
        if self.featuretype:
            self.featuretype = validate_feature_record(self.featuretype, 'Featuretype', models.SpatialFeatureType)

        data = {'layer_number': self.layer,
                'name_field': self.name_field, 'id_field': self.id_field,
                'feature_type': self.featuretype}

        if self.feature_types_file:
            with open(self.feature_types_file, 'rb') as f:
                types_file = default_storage.save(f'{SPATIAL_FILES_FOLDER}/{self.feature_types_file}', f)
                data['feature_types_file'] = types_file
                self.read_file_and_load_features(models.SpatialFeatureFile, data)
        else:
            self.read_file_and_load_features(models.SpatialFeatureFile, data)

    def all_files_exist(self):
        all_files, exists = [self.filename], True

        if self.feature_types_file:
            all_files.append(self.feature_types_file)

        for filename in all_files:
            if filename and not os.path.exists(filename):
                logger.error(f'Could not find file: {filename}')
                exists = False
        return exists


    def read_file_and_load_features(self, model, data):
        with open(self.filename, 'rb') as f:
            filename = default_storage.save(f'{SPATIAL_FILES_FOLDER}/{self.filename}', f)
            data['data'] = filename

            spatialfile = model(**data)
            spatialfile.save()
            load_spatial_features_from_files(str(spatialfile.id), model)

