import logging

from django.core.management.base import BaseCommand

from mapping import models
from mapping.tasks import load_spatial_features_from_files
from mapping.utils import DEFAULT_SOURCE_NAME, validate_feature_record
from utils.spatial import GeometryMapper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []

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
        self.featureset = options['featureset']
        self.spatialfile_id = options['spatialfile_id'] if options['spatialfile_id'] else self.spatialfile_id

        logger.info('Importing features from file: %s', self.filename)
        load_spatial_features_from_files.apply_async(args=(self.spatialfile_id, self.presentation))

    def add_arguments(self, parser):
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
