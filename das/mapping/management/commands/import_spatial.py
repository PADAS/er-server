# import geojson file (geofences) to dev db
import datetime
import logging
import os

from django.core.management.base import BaseCommand
from django.db import transaction

import utils.json
from mapping import models
from mapping.tasks import load_spatial_features
from mapping.utils import DEFAULT_SOURCE_NAME
from utils.spatial import GeometryMapper
from django.core.files import File

logger = logging.getLogger(__name__)


# TODO: merge this with importlayer.py.
class Command(BaseCommand):
    help = 'Import a spatial data layer'

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

        for input_filename in self.filename + [self.feature_types_file,]:
            print(f'Looking for file named {input_filename}')
            if not os.path.exists(input_filename):
                logger.error(f'Cannot find file: {input_filename}')
                return

        for input_spatial_file in self.filename:

            try:
                filecontents = File(open(input_spatial_file, 'rb'))
                types_filecontents = File(open(self.feature_types_file, 'rb'))

                spatialfile = models.SpatialFeatureFile.objects.create(
                    data=filecontents,
                    name_field=self.name_field,
                    id_field=self.id_field,
                    feature_types_file=types_filecontents,
                )
                transaction.on_commit(lambda: load_spatial_features(spatialfile))
            except Exception as err:
                logger.exception(err)

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, nargs='*',
                            help='spatial file, for example: import_spatial "roads.geojson"'
                                 ' --feature-types "spatial_feature_types.geojson"')
        parser.add_argument('--feature-types',
                            help='spatial feature types file', required=True)
        parser.add_argument(
            '--source', type=str, help=f'Source of data, default is {DEFAULT_SOURCE_NAME}')
        parser.add_argument('--spatialfile-id', type=str,
                            help='Spatial file ID')
