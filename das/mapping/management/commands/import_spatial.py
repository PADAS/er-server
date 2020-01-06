# import geojson file (geofences) to dev db
import logging
import datetime

from django.core.management.base import BaseCommand
from mapping import models
import utils.json
from utils.spatial import GeometryMapper

from mapping.utils import (DEFAULT_SOURCE_NAME, datasource_from_file,
                           save_feature_to_table, fields_iter)

logger = logging.getLogger(__name__)


TYPE_PROVENANCE_FIELDS = ('last_edited_user',
                          'last_edited_date',
                          'other_id')


def reduce_json(document):
    '''reduce python object fields to simple types, convert datetime to str'''
    if not isinstance(document, dict):
        return document

    reduced = {}
    for key, value in document.items():
        if isinstance(value, (datetime.date, datetime.datetime)):
            value = utils.json.date_to_isoformat(value)
        reduced[key] = value
    return reduced


class Command(BaseCommand):
    help = 'Import a spatial data layer'
    tmpdirs = []
    source_name = DEFAULT_SOURCE_NAME
    spatialfile_id = None

    geometry_mapper = GeometryMapper()

    def handle(self, *args, **options):
        self.source_name = options['source'] if options['source'] else DEFAULT_SOURCE_NAME
        self.spatialfile_id = options['spatialfile_id'] if options['spatialfile_id'] else self.spatialfile_id
        try:
            feature_types_file = options['feature_types']
            if feature_types_file:
                logger.info('Importing feature types from file: %s',
                            feature_types_file)
                data_source = datasource_from_file(feature_types_file, self.tmpdirs)
                self.import_feature_types(data_source)

            for filename in options['filename']:
                logger.info('Importing features from file: %s',
                            filename)
                data_source = datasource_from_file(filename, self.tmpdirs)
                self.import_layer(data_source)

        finally:
            data_source = None

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

    def import_layer(self, datasource):
        for feature in datasource[0]:
            logger.debug('Feature fields: %s', str(feature.fields))
            logger.debug('Feature geom type: %s', str(feature.geom_type))
            logger.debug('Feature length: %s', str(len(feature)))
            logger.debug('Feature num of fields: %s', str(feature.num_fields))
            save_feature_to_table(feature, self.source_name, self.spatialfile_id)

    def get_display_category(self, display_category_name, create_okay=True):
        try:
            display_category = models.DisplayCategory.objects.get_by_natural_key(
                display_category_name)
        except models.DisplayCategory.DoesNotExist:
            if create_okay:
                display_category = models.DisplayCategory.objects.create(
                    name=display_category_name)
            else:
                raise
        return display_category

    def import_feature_types(self, datasource, model=models.SpatialFeatureType):
        #{ "display_category": "POI", "attribute_schema": "{\"notes\":\"\"}\n", "created_user": "JOELM", "created_date": "2017\/07\/13 23:38:47", "last_edited_user": "JOELM", "last_edited_date": "2017\/07\/13 23:38:47", "globalid": "{0BBB7E88-8E7A-4E66-AA9F-2E9A7B259C5F}" }, "geometry": null },
        for feature in datasource[0]:
            fields = list(fields_iter(feature))
            global_id = feature['globalid'].value
            name = feature['type'].value

            provenance = {feature_name: feature[feature_name].value
                          for feature_name in fields if
                          feature_name in TYPE_PROVENANCE_FIELDS}
            provenance = reduce_json(provenance)

            attribute_schema = feature['attribute_schema'].value if 'attribute_schema' in fields else None
            if attribute_schema:
                try:
                    attribute_schema = utils.json.loads(attribute_schema)
                except utils.json.JSONDecodeError as ex:
                    logger.warning('FeatureType attribute_schema not JSON for globalid=%s: %s',
                                   global_id, ex)
                    attribute_schema = {}

            defaults = {'provenance': provenance, 'attribute_schema': attribute_schema,
                        'external_source': self.source_name}

            type_record, created = model.objects.get_or_create(
                name=name,
                defaults=defaults,
                display_category=self.get_display_category(
                    feature['display_category'].value),
                external_id=global_id)

            logger.debug('Import feature_type: %s, created:%s',
                         global_id, created)

            if 'tags' in fields:
                type_record.tags = [value.strip()
                                    for value in feature['tags'].value.split(',')]
            type_record.display_category = self.get_display_category(
                feature['display_category'].value)
            type_record.name = name
            for key, value in defaults.items():
                setattr(type_record, key, value)

            type_record.save()
