import datetime
import logging
import os
import tempfile
from zipfile import ZipFile

from arcgis.gis import GIS
from arcgis2geojson import arcgis2geojson
from django.conf import settings
from django.contrib import messages
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.gdal import GDALException
from django.core import management
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils.encoding import force_text

import utils.json
from mapping import models
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

ESRI_LINE = 'esriSLS'
ESRI_POLYGON = 'esriSFS'
ESRI_PMS = 'esriPMS'
ESRI_SMS = 'esriSMS'
ESRI_PFS = 'esriPFS'
RENDERER_TYPE_SIMPLE = 'simple'
RENDERER_TYPE_UNIQUE_VALUE = 'uniqueValue'
DEFAULT_IMAGE_WIDTH = 20
DEFAULT_IMAGE_HEIGHT = 20

DEFAULT_IMAGE = {
    "image": "/static/ranger_post-black.svg",
    "width": 20,
    "height": 20
}

DEFAULT_POLYGON = {
    "fill": "#f4d442",
    "stroke": "#000000",
    "fill-opacity": 0.2,
    "stroke-width": 1,
    "stroke-opacity": 0.7
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


def get_feature_type_name(feature, type_name=None):
    try:
        feature_type_name = type_name or feature['Types'].value if 'Types' in feature.fields else feature['type'].value
    except Exception:
        logger.warning('Feature %s Missing featuretype', feature['name'].value)
        return None

    return feature_type_name


def get_feature_type(type_name, create_okay=True):
    return models.SpatialFeatureType.objects.get_by_natural_key(type_name)

def save_feature_to_table(feature, source_name, spatialfile_id, featuretype=None, external_id=None, type_label=None):
    model = models.SpatialFeature
    if not external_id:
        external_id = feature['globalid'].value if 'globalid' in [x.lower() for x in feature.fields] \
            else feature['fid'].value

    fields = list(fields_iter(feature))

    # get wsf type from given type label
    if type_label:
        try:
            featuretype = feature[type_label].value
        except Exception:
            logger.warning(f'Type label given - {type_label} not a valid field for this feature')

    try:
        featuretype = featuretype or feature['Types'].value if 'Types' in feature.fields else feature['type'].value
    except Exception:
        logger.warning('Feature %s Missing featuretype', feature['name'].value)
        return

    feature_type, created = models.SpatialFeatureType.objects.get_or_create(name=feature_type_name)

    model_fieldname = 'feature_geometry'
    model_field_type = model._meta.get_field(model_fieldname)

    # With Esri integration we've seen some feature services give us json that has features with "geometry" missing
    # this handles and ignores that issue
    try:
        feature_geometry = geometry_mapper.get_db_geom(
            feature.geom, model_field_type)
    except GDALException as gex:
        logger.warning(f'Saving feature {external_id} raised GDALException: {gex}')
        return

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

    if not feature_record.name:
        feature_name = 'Names' if 'Names' in feature.fields else 'Name'
        try:
            feature_record.name = feature[feature_name].value
        except Exception:
            pass
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
    file_type_formats = {'shapefile': '.zip', 'geodatabase': '.gdb', 'geojson': ('.json', '.geojson')}
    for file_type, extension in file_type_formats.items():
        if f_type == file_type and not data_file.name.lower().endswith(extension):
            extension = ' or '.join(extension) if isinstance(extension, tuple) else extension
            raise ValidationError({field: [f'Kindly chose a {extension} file']})


message = messages.add_message


def arcgis_integration(request, obj):
    authenticated, group = arcgis_authentication(request, obj)
    group_conn = True
    if authenticated:
        if not group:
            message(request, messages.WARNING, f'Invalid group id: {obj.group_id}')
            group_conn = False

        elif "_testconnection" in request.POST:
            message(request, messages.INFO, f'Valid credentials. {group.title} group well configured')

        elif "_downloadfeatures" in request.POST:
            download_features_from_wfs(request, group, obj)
    else: 
        group_conn = False

    return group_conn


def arcgis_authentication(request, obj):
    try:
        gis = GIS(obj.service_url, username=obj.username, password=obj.password)
        return True, gis.groups.get(obj.group_id)
    except Exception as error:
        message(request, messages.ERROR, error)
        return False, None


import time


def download_features_from_wfs(request, group, obj):
    errored_files, success_files = [], []
    group_members = group.content() 
    for member in group_members:
        if member.type == "Feature Service" and member.title in items_to_import:
            title = member.title.replace(' ', '-')
            logger.info(f'processing {title}')
            success_files, errored_files = extract_gis_data(
                obj, member, title, errored_files, success_files)
    logger.info(f'returning. feature sync took {int(time.time() - ts)} seconds')
    wfs_download_return_messages(request, errored_files, success_files)


def extract_features(obj, member, title, data, success_files, simple_presentation):
    # todo: what if current dir is readonly?
    with open(f'./{title}.geojson', 'w') as data_file:
        data_file.write(data)
        management.call_command(
            'importlayer', 'importspatialfile', data_file.name, typelabel=obj.type_label,
            source=obj.source, name_field=obj.name_field, id_field=obj.id_field,
            presentation=simple_presentation
        )
        os.remove(data_file.name)
        success_files.append(member.title)
        return success_files


def extract_gis_data(obj, member, title, errored_files, success_files):
    data = None
    simple_presentation = None
    try:
        # Not handling multiple layers just yet.
        simple_presentation = import_featuretype_presentation(member.layers[0].properties.drawingInfo.renderer)
        data = member.layers[0].query().to_geojson
    except KeyError:
        logger.debug('to_geojson failed, trying to_json')
        data = arcgis2geojson(member.layers[0].query().to_json)
    except Exception as error:
        logger.info(f'Error reading from {member.title}', error)
        errored_files.append(member.title)
    if data:
        success_files = extract_features(obj, member, title, data, success_files, simple_presentation)
        return success_files, errored_files


def wfs_download_return_messages(request, errored_files, success_files):
    if len(errored_files) > 0:
        error_msg = f"Could not read data from {len(errored_files)} file(s): {', '.join(errored_files)}"
        message(request, messages.ERROR, error_msg) if request else logger.debug(error_msg)

    if len(success_files) > 0:
        success_msg = f'Features Successfully loaded into ER from {len(success_files)} file(s)'
        message(request, messages.SUCCESS, success_msg) if request else logger.info(success_msg)
    logger.info('Returning from download_features')


def import_featuretype_presentation(renderer):
    if renderer.type == RENDERER_TYPE_UNIQUE_VALUE:
        for unique_val in renderer.uniqueValueInfos:
            feature_type_name = unique_val.value
            presentation = get_mb_style(unique_val.symbol)
            logger.info(f'{feature_type_name}: {presentation}')
            if presentation:
                # Todo: revisit if we cache SFTs when importing features
                feature_type, created = models.SpatialFeatureType.objects.get_or_create(name=feature_type_name)
                feature_type.presentation = presentation
                feature_type.save()
    elif renderer.type == 'simple':
        simple_presentation = get_mb_style(renderer.symbol)
        logger.info(simple_presentation)
        return simple_presentation
    else:
        logger.info(f'Ignoring {renderer.type} renderer')


def get_mb_style(symbol):
    presentation = None
    type = symbol.type

    if type == ESRI_LINE:
        logger.debug('processing line')
        r, g, b, a = symbol.color
        width = symbol.width
        colors_as_hex = "#{:02x}{:02x}{:02x}".format(r, g, b)
        opacity = "{:.2f}".format(a / 255)
        presentation = {
            "stroke": colors_as_hex,
            "stroke-opacity": opacity,
            "stroke-width": width
        }
    elif type == ESRI_POLYGON:
        logger.debug('processing polygon')
        r, g, b, a = symbol.color
        fill_color = "#{:02x}{:02x}{:02x}".format(r, g, b)
        fill_opacity = "{:.2f}".format(a / 255)
        presentation = {
            "fill": fill_color,
            "fill-opacity": fill_opacity
        }
        if hasattr(symbol, 'outline') and symbol.outline:
            r, g, b, a = symbol.outline.color
            presentation["stroke"] = "#{:02x}{:02x}{:02x}".format(r, g, b)
            presentation["stroke-opacity"] = "{:.2f}".format(a / 255)
            presentation["stroke-width"] = symbol.outline.width
    elif type == ESRI_PMS or type == ESRI_PFS:
        logger.debug(f'processing picture symbol {type}')
        presentation = {
            "image": symbol.imageData,
            "width": symbol.width if hasattr(symbol, "width") else DEFAULT_IMAGE_WIDTH,
            "height": symbol.height if hasattr(symbol, "height") else DEFAULT_IMAGE_HEIGHT
        }
    elif type == ESRI_SMS:
        logger.debug('processing simple marker symbol')
        presentation = DEFAULT_IMAGE
    else:
        logger.info(f'Got type: {type}. Not handled yet.')

    return presentation
