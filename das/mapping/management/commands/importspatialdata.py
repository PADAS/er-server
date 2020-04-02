import logging
import os

from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from mapping import models
from mapping.tasks import load_spatial_features
from mapping.utils import (DEFAULT_SOURCE_NAME, default_id_field, default_layer,
                           default_name_field, validate_feature_record)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []
    SPATIALDATA_VERSIONS = ('v1', 'v2')

    def handle(self, *args, **options):
        self.source_name = options['source'] or DEFAULT_SOURCE_NAME
        self.filename = options['filename']
        self.name_field = options['name_field'] or default_name_field
        self.id_field = options['id_field'] or default_id_field
        self.layer = options['layer'] or default_layer
        self.utm = options['utm']
        self.featuretype = options['featuretype']
        self.featureset = options['featureset']
        self.feature_types_file = options['feature_types']
        self.spatialfile_id = options['spatialfile_id']

        spatialdata_version = options['spatialdata_version']
        if spatialdata_version not in self.SPATIALDATA_VERSIONS:
            raise NameError('Version: {0} not supported'.format(spatialdata_version))

        # validate upload file paths  
        for input_filename in self.filename + [self.feature_types_file,]:
            if input_filename and not os.path.exists(input_filename):
                logger.error(f'Could not find file: {input_filename}')
                return

        if spatialdata_version == self.SPATIALDATA_VERSIONS[0]:
            self.import_spatial_v1()
        else:
            self.import_spatial_v2()

    def add_arguments(self, parser):
        parser.add_argument('spatialdata_version', type=str,
                            help='supported versions are {0}, {1}'.format(self.SPATIALDATA_VERSIONS[0],
                                                                          self.SPATIALDATA_VERSIONS[1]))
        parser.add_argument('filename', type=str, nargs='*',
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

    def import_spatial_v1(self):
        if not self.featureset or not self.featuretype:
            logger.info('Ensure both featureset and featuretype are included in command, add flags --featureset and --featuretype')
            return
        
        featureset = validate_feature_record(self.featureset, 'Featureset', models.FeatureSet)
        featuretype = validate_feature_record(self.featuretype, 'Featuretype', models.FeatureType)

        data = {'layer_number': self.layer,
                'name_field': self.name_field, 'id_field': self.id_field,
                'feature_type': featuretype, 'feature_set': featureset}
        self.read_file_and_load_features(models.SpatialFile, data)

    def import_spatial_v2(self):
        if self.featuretype:
            self.featuretype = validate_feature_record(self.featuretype, 'Featuretype', models.SpatialFeatureType)

        data = {'layer_number': self.layer,
                'name_field': self.name_field, 'id_field': self.id_field,
                'feature_type': self.featuretype}

        if self.feature_types_file:
            types_file = File(open(self.feature_types_file, 'rb'))
            data['feature_types_file'] = types_file
        self.read_file_and_load_features(models.SpatialFeatureFile, data)

    def read_file_and_load_features(self, model, data):
        for input_spatial_file in self.filename:
            try:
                data['data'] = File(open(input_spatial_file, 'rb'))
                spatialfile = model(**data)
                spatialfile.save()
                transaction.on_commit(lambda: load_spatial_features(spatialfile))
            except Exception as err:
                logger.exception(err)
