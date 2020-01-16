import datetime
import logging
import tempfile
from django.core.exceptions import ValidationError
from zipfile import ZipFile

from django.conf import settings
from django.contrib.gis.gdal import DataSource
from django.db.utils import IntegrityError
from django.utils.encoding import force_text

import utils.json
from mapping import models
# from mapping.models import (SpatialFeature, SpatialFeatureType)
from utils.spatial import GeometryMapper

geometry_mapper = GeometryMapper()

logger = logging.getLogger(__name__)
MAPPING_FEATURES_V2 = getattr(settings, 'MAPPING_FEATURES_V2', False)


def shortname_validator(value):
    if value:
        value = value[:25]
    return value


DEFAULT_SOURCE_NAME = 'STE'

PROVENANCE_FIELDS = ('collect_user', 'collect_method', 'collect_date',
                     'ground_verified', 'spatial_feature_owners',
                     'spatial_data_owners',
                     'created_user', 'created_date', 'last_edited_user',
                     'last_edited_date',
                     'other_id')

ATTRIBUTES_TO_SPATIAL_MAPPING = {'short_name': {'field': 'short_name', 'validator': shortname_validator},
                                 'name': {'field': 'name', 'validator': lambda v: v}
                                 }


def validate_feature_record(record, record_name, model):
    if isinstance(record, str):
        try:
            return model.objects.get(name=record)
        except Exception:
            logger.error(f'{record_name} {record} does not exist')
            exit()
    return record


def datasource_from_file(filename, tmpdirs):  # geojson file
    if filename.endswith('kmz'):
        tmpdir = tempfile.TemporaryDirectory()
        tmpdirs.append(tmpdir)
        zip = ZipFile(filename)
        filename = zip.extract('doc.kml', tmpdir.name)  # use break
    return DataSource(filename)


def fields_iter(feature):
    for field_name in feature.fields:
        yield force_text(field_name)


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


def get_feature_type(type_name, create_okay=True):
    return models.SpatialFeatureType.objects.get_by_natural_key(type_name)


def save_feature_to_table(feature, source_name, spatialfile_id, featuretype=None, external_id=None):
    model = models.SpatialFeature
    if not external_id:
        external_id = feature['globalid'].value if 'globalid' in feature.fields \
            else feature['fid'].value

    fields = list(fields_iter(feature))
    featuretype = featuretype or feature['type'].value

    try:
        feature_type = get_feature_type(featuretype)
    except models.SpatialFeatureType.DoesNotExist:
        logger.warning('SpatielFeatureType %s not found for %s',
                       featuretype, external_id)
        return

    model_fieldname = 'feature_geometry'
    model_field_type = model._meta.get_field(model_fieldname)
    feature_geometry = geometry_mapper.get_db_geom(
        feature.geom, model_field_type)

    attribute_fields = feature_type.attribute_schema

    attributes = {feature_name: feature[feature_name].value
                  for feature_name in fields if
                  feature_name in attribute_fields}
    attributes = reduce_json(attributes)

    provenance = {feature_name: feature[feature_name].value
                  for feature_name in fields if
                  feature_name in PROVENANCE_FIELDS}
    provenance = reduce_json(provenance)

    defaults = {'attributes': attributes, 'provenance': provenance,
                'external_source': source_name}
    for attribute_field, spatial_field in ATTRIBUTES_TO_SPATIAL_MAPPING.items():
        if attribute_field in fields:
            defaults[spatial_field['field']] = spatial_field['validator'](
                feature[attribute_field].value)
    try:

        created = False
        feature_record = model.objects.get(external_id=external_id)
    except model.DoesNotExist:
        feature_record = None

    if not feature_record:
        try:
            feature_record = model.objects.create_spatialfeature(
                feature_geometry=feature_geometry,
                feature_type=feature_type,
                external_id=external_id)
            created = True
        except IntegrityError:
            logger.warning('Feature has null geometry: global_id=%s, %s',
                           external_id, defaults)
            return

    logger.debug('Import feature: %s, created:%s',
                 external_id, created)

    feature_record.feature_type = feature_type

    if 'tags' in feature.fields:
        feature_record.tags = [value.strip()
                               for value in feature['tags'].value.split(',')]
    feature_record.feature_geometry = feature_geometry
    for key, value in defaults.items():
        setattr(feature_record, key, value)
    feature_record = save_spatial_file(spatialfile_id, models.SpatialFeatureFile, feature_record)
    feature_record.save()


def save_spatial_file(spatialfile_id, model, record):
    if spatialfile_id:
        spatialfile = model.objects.get(id=spatialfile_id)
        record.spatialfile = spatialfile
        return record


def check_file_extension(f_type, data_file, feature_types_file):
    validate_file_type(f_type, data_file, 'data')
    if feature_types_file:
        validate_file_type(f_type, feature_types_file, 'feature_types_file')


def validate_file_type(f_type, data_file, field):

    # import pdb; pdb.set_trace()
    file_type_formats = {'shapefile': '.zip', 'geodatabase': '.gdb', 'geojson': ('.json', '.geojson')}
    for file_type, extension in file_type_formats.items():
        if f_type == file_type and not data_file.name.lower().endswith(extension):
            extension = ' or '.join(extension) if isinstance(extension, tuple) else extension
            raise ValidationError({field: [f'Kindly chose a {extension} file']})

