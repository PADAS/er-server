import datetime
import logging
import os
import shutil
import tempfile
from zipfile import ZipFile


from django.conf import settings
from django.contrib.gis.gdal import DataSource
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils.encoding import force_text


import utils.json
from mapping import models
# from mapping.tasks import load_features_from_wfs
from utils.spatial import GeometryMapper

geometry_mapper = GeometryMapper()

logger = logging.getLogger(__name__)
MAPPING_FEATURES_V2 = getattr(settings, 'MAPPING_FEATURES_V2', False)


FEATURE_TYPES = {
    'Primary': 'Primary Roads',
    'Secondary': 'Secondary Roads',
    'Old': 'Old Roads',
    'Tertiary': 'Tertiary Roads',
}

TYPE_PROVENANCE_FIELDS = ('last_edited_user',
                          'last_edited_date',
                          'other_id')

DEFAULT_SOURCE_NAME = 'STE'

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


def validate_feature_record(record, record_name, model):
    if isinstance(record, str):
        try:
            return model.objects.get(name=record)
        except Exception:
            logger.error(f'{record_name} {record} does not exist')
            exit()
    return record


def make_external_id(id_field, name_field, layer, feature, arc_item_id=None):
    name_value = ''
    id_value = ''
    for name in feature.fields:
        if id_field and name.lower() == id_field.lower():
            id_value = str(feature[name].value)
        elif name_field and name.lower() == name_field.lower():
            name_value = str(feature[name].value)
    if arc_item_id:
        return '-'.join((str(arc_item_id), name_value, id_value))
    return '-'.join((layer.name, name_value, id_value))


def contains_unique_keys_in_layer(id_field, name_field, layer):
    seen = set()
    unique_keys = True
    for feature in layer:
        external_id = make_external_id(id_field, name_field, layer, feature)
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
        logger.warning(f'Given layer {layer} should be less than existing layers: {datasource.layer_count}')
        layer_num = 0
    return datasource, layer_num


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


def get_spatial_feature_type(feature, type_field=None, featuretype=None):
    try:
        return models.SpatialFeatureType.objects.get(name=featuretype)
    except Exception:
        type_name = None
        # get wfs type from given type label
        if type_field:
            try:
                type_name = feature.get(type_field)
            except Exception:
                logger.warning(f'Type label given - {type_field} not a valid field for this feature')

        if not type_name:
            try:
                # todo: eventually remove Types
                type_name = feature.get('FeatureType') if 'FeatureType' in feature.fields else feature.get(
                    'Types') if 'Types' in feature.fields else feature.get('type')
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
def set_feature_name(feature_record, feature, feature_type, counter):
    if not feature_record.name.strip():
        feature_name = 'Names' if 'Names' in feature.fields else 'Name'
        try:
            feature_record.name = feature.get(feature_name)
        except Exception:
            pass

    # if still not set, use type & counter
    if not feature_record.name.strip():
        feature_record.name = feature_type.name + str(counter)


def get_or_create_feature(external_id, attributes):
    created = False
    try:
        feature_record = models.SpatialFeature.objects.get(external_id=external_id)
    except models.SpatialFeature.DoesNotExist:
        feature_record = None

    if not feature_record:
        try:
            attributes.update(external_id=external_id)
            feature_record = models.SpatialFeature.objects.create_spatialfeature(**attributes)
            created = True
        except IntegrityError as ie:
            logger.exception(ie)

    return feature_record, created


def mappingv2_save_spatial_data(feature, featuretype, source_name, spatialfile_id, external_id=None):
    model = models.SpatialFeature
    if not external_id:
        external_id = feature['globalid'].value if 'globalid' in feature.fields \
            else feature['fid'].value
    feature_type = get_spatial_feature_type(feature, featuretype=featuretype)
    if not feature_type:
        return

    fields = list(fields_iter(feature))
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

    feature_record, created = get_or_create_feature(external_id, dict(feature_geometry=feature_geometry,
                                                                      feature_type=feature_type))

    if not feature_record:
        return

    logger.debug('Import feature: %s, created:%s', external_id, created)

    feature_record.feature_type = feature_type

    if 'tags' in feature.fields:
        feature_record.tags = [value.strip()
                               for value in feature['tags'].value.split(',')]
    feature_record.feature_geometry = feature_geometry
    for key, value in defaults.items():
        setattr(feature_record, key, value)
    save_spatial_file(spatialfile_id, models.SpatialFeatureFile, feature_record)
    feature_record.save()


def save_spatial_file(spatialfile_id, model, record):
    if spatialfile_id:
        spatialfile = model.objects.get(id=spatialfile_id)
        record.spatialfile = spatialfile


def check_file_extension(f_type, data_file, feature_types_file):
    validate_file_type(f_type, data_file, 'data')
    if feature_types_file:
        validate_file_type(f_type, feature_types_file, 'feature_types_file')


def validate_file_type(f_type, data_file, field):
    file_type_formats = {'shapefile': '.zip', 'geodatabase': '.gdb', 'geojson': ('.json', '.geojson')}
    for file_type, extension in file_type_formats.items():
        if f_type == file_type and not data_file.name.lower().endswith(extension):
            extension = ' or '.join(extension) if isinstance(extension, tuple) else extension
            raise ValidationError({field: [f'Kindly chose a {extension} file']})


def import_layer(layer, source_name, spatialfile_id, featuretype, featureset, id_field, name_field):
    logger.info('Importing layer: %s, type: %s, fields: %s',
                layer.name, layer.geom_type, layer.fields)

    has_unique_keys = contains_unique_keys_in_layer(id_field, name_field, layer)

    for i, feature in enumerate(layer):
        external_id = make_external_id(id_field, name_field, layer, feature)
        if not has_unique_keys:
            external_id = external_id + '-' + str(i)
        if featureset:
            mappingv1_save_spatial_data(feature, featureset, featuretype, external_id, name_field, spatialfile_id)
        else:
            mappingv2_save_spatial_data(feature, featuretype, source_name, spatialfile_id, external_id)


def cleanup_files(filename):
    """
    Remove files/directories from the temporary folder.
    """
    pathlist = filename.split("/")
    name = pathlist[-1]

    if 'json' not in name and len(pathlist) > 8:
        name = pathlist[-2] + '.zip'

    uploaded_file_directory = '/'.join(pathlist[:7])
    uploaded_file_path = uploaded_file_directory + "/" + name

    try:
        if os.path.exists(uploaded_file_path):
            os.remove(uploaded_file_path)
        shutil.rmtree(uploaded_file_directory)
    except PermissionError:
        logger.exception(
            f'Cleaning up spatial files after import: {uploaded_file_directory}')
    filename = ''


def mappingv1_save_spatial_data(feature, featureset, featuretype, external_id, name_field, spatialfile_id):
    fields = {}
    for name in feature.fields:
        if name.lower() in (name_field.lower(), 'description'):
            continue
        value = feature[name].value
        if isinstance(value, datetime.date):
            value = value.isoformat()
        fields[name] = value
    try:
        feature_model = get_feature_class(feature.geom_type.name)
    except KeyError as ke:
        feature_model = get_feature_class(str(feature.geom))
    model_fieldname = 'feature_geometry'
    model_field_type = feature_model._meta.get_field(model_fieldname)
    feature_geometry = geometry_mapper.get_db_geom(
        feature.geom, model_field_type)
    defaults = {'feature_geometry': feature_geometry, 'fields': fields}
    feature_record, created = feature_model.objects.get_or_create(
        defaults=defaults,
        featureset=models.FeatureSet.objects.get(name=featureset),
        type=get_featuretype_for_feature(feature, default=featuretype),
        external_id=external_id)

    logger.debug('Import feature: %s, created:%s',
                 external_id, created)

    feature_record.feature_geometry = feature_geometry
    feature_record.fields = fields
    try:
        feature_record.name = feature[name_field].value
    except (KeyError, IndexError):
        pass
    try:
        feature_record.description = feature['Description'].value
    except (KeyError, IndexError):
        pass
    save_spatial_file(spatialfile_id, models.SpatialFile, feature_record)
    feature_record.save()


def get_feature_class(name):
    name_lower = name.lower()
    if 'polygon' in name_lower:
        return models.PolygonFeature
    if 'linestring' in name_lower:
        return models.LineFeature
    if 'point' in name_lower:
        return models.PointFeature
    raise KeyError('DAS Feature class not found for {0}'.format(name))


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


def import_feature_types(datasource, source_name):
    model = models.SpatialFeatureType
    for feature in datasource:
        fields = list(fields_iter(feature))
        global_id = feature['globalid'].value
        name = feature['type'].value

        try:
            type_record, created = model.objects.get_or_create(name=name)
            display_category = get_display_category(feature['display_category'].value)
        except IntegrityError as err:
            logger.warning(err)
            return
        except Exception as error:
            raise ValidationError({'feature_types_file': ["Unable to process file: ", error]})

        type_record.display_category = display_category
        type_record.external_id = global_id

        provenance = {feature_name: feature[feature_name].value for feature_name in fields if
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
                    'external_source': source_name}

        if 'tags' in fields:
            type_record.tags = [value.strip()
                                for value in feature['tags'].value.split(',')]
        for key, value in defaults.items():
            setattr(type_record, key, value)

        type_record.save()
        logger.debug('Import feature_type: %s, created:%s',
                     global_id, created)
