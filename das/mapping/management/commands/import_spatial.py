# import geojson file (geofences) to dev db
import datetime
import logging

from django.core.management.base import BaseCommand

import utils.json
from mapping import models
from mapping.tasks import load_spatial_features_from_files
from mapping.utils import DEFAULT_SOURCE_NAME
from mapping.ste_utils import create_local_spatialfiles_folder
import shutil
from utils.spatial import GeometryMapper

logger = logging.getLogger(__name__)


# TODO: merge this with importlayer.py.
class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []
    source_name = DEFAULT_SOURCE_NAME
    spatialfile_id = None

    geometry_mapper = GeometryMapper()

    def handle(self, *args, **options):
        self.source_name = options['source'] if options['source'] else DEFAULT_SOURCE_NAME
        self.spatialfile_id = options['spatialfile_id'] if options['spatialfile_id'] else self.spatialfile_id
        self.filename = options['filename']
        self.feature_types_file = options['feature_types']
        self.name_field = options['name_field'] if options.get('name_field') else 'Name'
        self.id_field = options['id_field'] if options.get('id_field') else 'globalid'

        if self.spatialfile_id:
            self.load_features(self.spatialfile_id)
        else:
            try:
                create_local_spatialfiles_folder()
                self.filename = shutil.copy(self.filename, 'mapping/spatialfiles')
                self.feature_types_file = shutil.copy(self.feature_types_file, 'mapping/spatialfiles')

                spatialfile = models.SpatialFeatureFile.objects.create(
                    data = self.filename,
                    name_field= self.name_field,
                    id_field= self.id_field,
                    feature_types_file = self.feature_types_file
                )
                self.load_features(spatialfile.id)
            except Exception as err:
                logger.info(err)


    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, nargs='*',
                            help='spatial file, for example: import_spatial "roads.geojson"'
                                 ' --feature-types "spatial_feature_types.geojson"')
        parser.add_argument('--feature-types',
                            help='spatial feature types file')
        parser.add_argument(
            '--source', type=str, help=f'Source of data, default is {DEFAULT_SOURCE_NAME}')
        parser.add_argument('--spatialfile-id', type=str,
                            help='Spatial file ID')

    def load_features(self, spatialfile_id):
        logger.info('Importing features from file: %s', self.filename)
        load_spatial_features_from_files.apply_async(args=(str(spatialfile_id),))
