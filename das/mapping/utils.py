import datetime
import logging
import tempfile
import urllib.parse as urlparse
import zipfile
from urllib.parse import urlencode

from simplejson.scanner import JSONDecodeError

from django.conf import settings
from django.contrib.gis.gdal import DataSource
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils.encoding import force_str

import utils.json
from mapping import models
from utils.spatial import GeometryMapper

geometry_mapper = GeometryMapper()

logger = logging.getLogger(__name__)
SPATIAL_FILES_FOLDER = getattr(
    settings, 'SPATIAL_FILES_FOLDER', 'mapping/spatialfiles')


FEATURE_TYPES = {
    'Primary': 'Primary Roads',
    'Secondary': 'Secondary Roads',
    'Old': 'Old Roads',
    'Tertiary': 'Tertiary Roads',
}

TYPE_PROVENANCE_FIELDS = ('last_edited_user',
                          'last_edited_date',
                          'other_id')

DEFAULT_SOURCE_NAME = 'default'

PROVENANCE_FIELDS = ('collect_user', 'collect_method', 'collect_date',
                     'ground_verified', 'spatial_feature_owners',
                     'spatial_data_owners',
                     'created_user', 'created_date', 'last_edited_user',
                     'last_edited_date',
                     'other_id')


def shortname_validator(value):
    if value:
        value = value[:25]
    return value


ATTRIBUTES_TO_SPATIAL_MAPPING = {'short_name': {'field': 'short_name', 'validator': shortname_validator},
                                 'name': {'field': 'name', 'validator': lambda v: v}
                                 }

default_name_field = 'Name'
default_id_field = 'globalid'
default_layer = 0


def validate_feature_record(record, record_name, model):
    try:
        return model.objects.get(name=record)
    except Exception:
        logger.error(f'{record_name} {record} does not exist')
        exit()


def make_external_id(layer, feature, id_field, name_field, arc_item_id=None):
    id_field = id_field or default_id_field
    name_field = name_field or default_name_field
    name_value, id_value = '', ''
    for name in feature.fields:
        if name.lower() == id_field.lower():
            id_value = str(feature[name].value)
        elif name.lower() == name_field.lower():
            name_value = str(feature[name].value)
    if arc_item_id:
        return '-'.join((str(arc_item_id), name_value, id_value))
    return '-'.join((layer.name, name_value, id_value))


def contains_unique_keys_in_layer(id_field, name_field, layer):
    seen = set()
    unique_keys = True
    for feature in layer:
        external_id = make_external_id(layer, feature, id_field, name_field)
        if external_id in seen:
            logger.info('External_id=%s not unique to layer', external_id)
            unique_keys = False
            break
        else:
            seen.add(external_id)
    return unique_keys


def get_datasource_and_layer_num(filename, tmpdirs=None, layer=None):
    datasource = datasource_from_file(filename, tmpdirs)
    logger.debug('Data Source: %s, layercount %s',
                 datasource.name, datasource.layer_count)
    if datasource.layer_count > 1 and layer is None:
        logger.warning('multiple layers not supported...')
        for i in range(0, datasource.layer_count):
            logger.info('layer: %s, name: %s', i, datasource[i].name)
        return

    layer_num = 0 if layer is None else layer
    if layer_num >= datasource.layer_count:
        logger.warning(
            f'Given layer {layer} should be less than existing layers: {datasource.layer_count}')
        layer_num = 0
    return datasource, layer_num


def datasource_from_file(filename, tmpdirs):  # geojson file
    if filename.endswith('kmz'):
        tmpdir = tempfile.TemporaryDirectory()
        tmpdirs.append(tmpdir)
        zip = zipfile.ZipFile(filename)
        filename = zip.extract('doc.kml', tmpdir.name)  # use break
    return DataSource(filename)


def fields_iter(feature):
    for field_name in feature.fields:
        yield force_str(field_name)


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


def get_spatial_feature_type_name(feature, type_label):
    if type_label:
        return feature.get(type_label) if type_label in feature.fields else None


def get_or_create_spatial_feature_type(feature, type_label=None):
    type_name = get_spatial_feature_type_name(feature, type_label)

    if not type_name:
        try:
            type_name = feature.get(
                'FeatureType') if 'FeatureType' in feature.fields else feature.get('type')
        except Exception:
            logger.warning('%s missing featuretype', str(feature))
            return

    if type_name:
        try:
            return models.SpatialFeatureType.objects.get_or_create(name=type_name)[0]
        except IntegrityError as ie:
            logger.warning(ie)
            return


# set feature name to some reasonable default if we can't find a name
def set_feature_name(feature_record, feature, feature_type, name_field, counter):
    name_field = name_field or default_name_field
    try:
        feature_record.name = feature.get(name_field)
    except Exception:
        feature_record.name = feature_type.name + str(counter)


def get_or_create_feature(attributes):
    created = False
    try:
        feature_record = models.SpatialFeature.objects.get(
            external_id=attributes.get('external_id'))
    except models.SpatialFeature.DoesNotExist:
        feature_record = None

    if not feature_record:
        try:
            feature_record = models.SpatialFeature.objects.create_spatialfeature(
                **attributes)
            created = True
        except IntegrityError as ie:
            logger.exception(ie)

    return feature_record, created


def mappingv2_save_spatial_data(feature, external_id, spatialfile, counter=0):
    model = models.SpatialFeature
    feature_type = spatialfile.feature_type if spatialfile.feature_type else get_or_create_spatial_feature_type(
        feature)
    if not feature_type:
        return

    fields = list(fields_iter(feature))
    model_fieldname = 'feature_geometry'
    model_field_type = model._meta.get_field(model_fieldname)
    feature_geometry = geometry_mapper.get_db_geom(
        feature.geom, model_field_type)
    data = {
        'external_id': external_id,
        'feature_geometry': feature_geometry,
        'feature_type': feature_type}

    feature_record, created = get_or_create_feature(data)
    if not feature_record:
        return
    feature_record.feature_type = feature_type
    feature_record.feature_geometry = feature_geometry

    attribute_fields = feature_type.attribute_schema

    attributes = {feature_name: feature[feature_name].value
                  for feature_name in fields if
                  feature_name in attribute_fields}
    attributes = reduce_json(attributes)

    provenance = {feature_name: feature[feature_name].value
                  for feature_name in fields if
                  feature_name in PROVENANCE_FIELDS}
    provenance = reduce_json(provenance)
    source = getattr(spatialfile, 'source', DEFAULT_SOURCE_NAME)

    defaults = {'attributes': attributes, 'provenance': provenance,
                'external_source': source}
    for attribute_field, spatial_field in ATTRIBUTES_TO_SPATIAL_MAPPING.items():
        if attribute_field in fields:
            defaults[spatial_field['field']] = spatial_field['validator'](
                feature[attribute_field].value)

    logger.debug('Import feature: %s, created:%s', external_id, created)
    feature_record.spatialfile = spatialfile

    if 'tags' in feature.fields:
        feature_record.tags = [value.strip()
                               for value in feature['tags'].value.split(',')]
    for key, value in defaults.items():
        setattr(feature_record, key, value)
    set_feature_name(feature_record, feature, feature_type,
                     spatialfile.name_field, counter)
    if hasattr(feature_record, "short_name") and not feature_record.short_name:
        feature_record.short_name = ""
    feature_record.clean()
    feature_record.save()


def check_file_extension(f_type, data_file, feature_types_file):
    validate_file_type(f_type, data_file, 'data')
    if feature_types_file:
        validate_file_type(f_type, feature_types_file, 'feature_types_file')


def validate_file_type(f_type, data_file, field):
    file_type_formats = {'shapefile': '.zip',
                         'geodatabase': '.gdb', 'geojson': ('.json', '.geojson')}
    for file_type, extension in file_type_formats.items():
        if f_type == file_type and not data_file.name.lower().endswith(extension):
            extension = ' or '.join(extension) if isinstance(
                extension, tuple) else extension
            raise ValidationError(
                {field: [f'Kindly chose a {extension} file']})


def import_layer(layer, spatialfile):
    logger.info('Importing layer: %s, type: %s, fields: %s',
                layer.name, layer.geom_type, layer.fields)

    has_unique_keys = contains_unique_keys_in_layer(
        spatialfile.id_field, spatialfile.name_field, layer)
    for i, feature in enumerate(layer):
        if feature.geom.empty:
            continue
        else:
            load_layer(layer, feature, i, spatialfile, has_unique_keys)


def load_layer(layer, feature, i, spatialfile, has_unique_keys):
    external_id = make_external_id(
        layer, feature, spatialfile.id_field, spatialfile.name_field)
    if not has_unique_keys:
        external_id = external_id + '-' + str(i)
    if spatialfile.__class__.__name__ == 'SpatialFile':
        mappingv1_save_spatial_data(feature, external_id, spatialfile)
    else:
        mappingv2_save_spatial_data(feature, external_id, spatialfile)


def mappingv1_save_spatial_data(feature, external_id, spatialfile, counter=0):
    geometry_mapper = GeometryMapper()
    fields = {}
    name_field = spatialfile.name_field or default_name_field
    for name in feature.fields:
        if name.lower() in (name_field.lower(), 'description'):
            continue
        value = feature[name].value
        if isinstance(value, datetime.date):
            value = value.isoformat()
        fields[name] = value
    try:
        feature_model = get_feature_class(feature.geom_type.name)
    except KeyError:
        feature_model = get_feature_class(str(feature.geom))
    model_fieldname = 'feature_geometry'
    model_field_type = feature_model._meta.get_field(model_fieldname)
    feature_geometry = geometry_mapper.get_db_geom(
        feature.geom, model_field_type)
    defaults = {'feature_geometry': feature_geometry, 'fields': fields}
    feature_type = get_featuretype_for_feature(
        feature, default=spatialfile.feature_type)
    feature_record, created = feature_model.objects.get_or_create(
        defaults=defaults,
        featureset=models.FeatureSet.objects.get(name=spatialfile.feature_set),
        type=feature_type,
        external_id=external_id)

    logger.debug('Import feature: %s, created:%s',
                 external_id, created)

    feature_record.feature_geometry = feature_geometry
    feature_record.fields = fields
    set_feature_name(feature_record, feature, feature_type,
                     spatialfile.name_field, counter)
    feature_record.spatialfile = spatialfile
    logger.debug('Import feature: %s, created:%s', external_id, created)

    try:
        feature_record.description = feature['Description'].value
    except (KeyError, IndexError):
        pass
    feature_record.save()


def get_feature_class(name):
    name_lower = name.lower()
    if 'polygon' in name_lower:
        return models.PolygonFeature
    if 'linestring' in name_lower:
        return models.LineFeature
    if 'point' in name_lower:
        return models.PointFeature
    raise KeyError('EarthRanger Feature class not found for {0}'.format(name))


def get_featuretype_for_feature(feature, default=None):
    type_name = default
    for name in feature.fields:
        if name in ('roadclass',):
            value = feature[name].value
            type_name = FEATURE_TYPES[value]
    if type_name:
        featuretype = models.FeatureType.objects.get_by_natural_key(
            type_name)
        return featuretype
    else:
        raise KeyError('no default featuretype specified')


def get_display_category(display_category_name, create_okay=True):
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


def import_feature_types(datasource, source_name=DEFAULT_SOURCE_NAME):
    model = models.SpatialFeatureType
    for feature in datasource:
        fields = list(fields_iter(feature))
        global_id = feature['globalid'].value
        name = feature['type'].value

        try:
            type_record, created = model.objects.get_or_create(name=name)
            display_category = get_display_category(
                feature['display_category'].value)
        except IntegrityError as err:
            logger.warning(err)
            return
        except Exception as error:
            raise ValidationError(
                {'feature_types_file': ["Unable to process file: ", error]})

        type_record.display_category = display_category
        type_record.external_id = global_id

        provenance = {feature_name: feature[feature_name].value for feature_name in fields if
                      feature_name in TYPE_PROVENANCE_FIELDS}
        provenance = reduce_json(provenance)

        attribute_schema = feature['attribute_schema'].value if 'attribute_schema' in fields else None
        if attribute_schema:
            try:
                attribute_schema = utils.json.loads(attribute_schema)
            except JSONDecodeError as ex:
                logger.warning('FeatureType attribute_schema not JSON for globalid=%s: %s',
                               global_id, ex)
                attribute_schema = {}

        defaults = {'provenance': provenance, 'attribute_schema': attribute_schema,
                    'external_source': source_name}

        if 'tags' in fields:
            type_record.tags = [value.strip()
                                for value in feature['tags'].value.split(',')]
        for key, value in defaults.items():
            setattr(type_record, key, value)

        type_record.save()
        logger.debug('Import feature_type: %s, created:%s',
                     global_id, created)


def clear_features(obj):
    # Incase of a new spatialfile clear initially created features
    tables = [models.SpatialFeature, models.LineFeature,
              models.PointFeature, models.PolygonFeature]
    for table in tables:
        try:
            table.objects.filter(spatialfile=obj).delete()
        except Exception:
            pass


def construct_url_param(redirect_url, params):
    url_parts = list(urlparse.urlparse(redirect_url))
    url_parts[4] = urlencode(params)
    return urlparse.urlunparse(url_parts)
