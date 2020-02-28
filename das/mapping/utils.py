import datetime
import logging
import os
import shutil
import tempfile
from zipfile import ZipFile

import arcgis
from django.conf import settings
from django.contrib import messages
from django.contrib.gis.gdal import DataSource, GDALException
from django.core import management
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe

import utils.json
from arcgis2geojson import arcgis2geojson
from mapping import models
from mapping.tasks import background_download_features_from_wfs
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


def get_spatial_feature_type(feature, type_label, featuretype):
    try:
        return models.SpatialFeatureType.objects.get(name=featuretype)
    except Exception:
        type_name = None
        # get wfs type from given type label
        if type_label:
            try:
                type_name = feature.get(type_label)
            except Exception:
                logger.warning(f'Type label given - {type_label} not a valid field for this feature')

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


def mappingv2_save_spatial_data(feature, featuretype, source_name, spatialfile_id, external_id=None, type_label=None, counter=0):
    model = models.SpatialFeature

    # this only happens when called from import_spatial
    if not external_id:
        external_id = feature.get('globalid') if 'globalid' in [x.lower() for x in feature.fields] else feature.get(
            'fid')
    feature_type = get_spatial_feature_type(feature, type_label, featuretype)
    if not feature_type:
        return

    fields = list(fields_iter(feature))
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

    created = False
    try:
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
    set_feature_name(feature_record, feature, feature_type, counter)
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


# TODO: at some point should move out arcgis-specific code into its own module/class

message = messages.add_message


def arcgis_integration(request, obj):
    # could optimize by authenticating conditionally
    gis = arcgis_authentication(request, obj)
    if gis:
        acrgis_groups_found = search_groups(gis, obj)
        if "_testconnection" in request.POST:
            message(request, messages.INFO, f'Successful Configuration')
        elif "_downloadfeatures" in request.POST:
            # set to a background task
            try:
                task_started_msg = "Features download in progress, checkout loaded <a href='/admin/mapping/spatialfeature/'>spatialfeatures</a> after a few minutes"
                message(request, messages.INFO, mark_safe(task_started_msg))
                background_download_features_from_wfs.apply_async(args=(obj.id,))
            except Exception as ex:
                error_msg = f"Select a group to enable features download"
                message(request, messages.ERROR,ex) if request else logger.debug(error_msg)
                logger.exception(ex)
        return acrgis_groups_found


def search_groups(gis, obj):
    # search for groups only within the user's org if serchtext blank/empty else search for groups outside
    # the user's org as well.
    groups = gis.groups.search() if not obj.search_text \
        else gis.groups.search(
        query=obj.search_text, outside_org=True, max_groups=100)
    return groups


def update_db_groups(wfs_groups, obj):
    # this will cleanup if FK is at the other end of the relationship
    my_groups = models.ArcgisGroup.objects.filter(config_id=obj.id)
    wfs_group_ids = [g.id for g in wfs_groups]

    for _group in my_groups:
        # clear groups deleted on arcgis account
        if _group.group_id not in wfs_group_ids:
            _group.delete()

    for group in wfs_groups:
        models.ArcgisGroup.objects.get_or_create(
            name=group.title,
            group_id=group.id,
            config_id=obj.id
        )


def arcgis_authentication(request, obj):
    try:
        gis = arcgis.gis.GIS(obj.service_url, username=obj.username, password=obj.password)
        return gis
    except Exception as error:
        message(request, messages.ERROR, error) if request else logger.exception(error)


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


def extract_features(obj, member, title, data, success_files, simple_presentation):
    with tempfile.NamedTemporaryFile() as data_file:
        data_file.write(data.encode())
        data_file.flush()
        data_file.seek(0)
        logger.info(f'Importing {title} features from tempfile {data_file.name}')
        management.call_command(
            'importlayer', 'importspatialfile', data_file.name, typelabel=obj.type_label,
            source=obj.source, name_field=obj.name_field, id_field=obj.id_field,
            presentation=simple_presentation
        )
        success_files.append(member.title)
        return success_files


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
            logger.debug(f'{feature_type_name}: {presentation}')
            if presentation:
                feature_type, created = models.SpatialFeatureType.objects.get_or_create(name=feature_type_name)
                feature_type.presentation = presentation
                feature_type.save()
    elif renderer.type == 'simple':
        simple_presentation = get_mb_style(renderer.symbol)
        # logger.info(simple_presentation)
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
            "image": f"data:image/png;base64,{symbol.imageData}",
            "width": symbol.width if hasattr(symbol, "width") else DEFAULT_IMAGE_WIDTH,
            "height": symbol.height if hasattr(symbol, "height") else DEFAULT_IMAGE_HEIGHT
        }
    elif type == ESRI_SMS:
        logger.debug('processing simple marker symbol')
        presentation = DEFAULT_IMAGE
    else:
        logger.info(f'Got type: {type}. Not handled yet.')

    return presentation


def get_datasource_and_layer_num(filename, tmpdirs, layer):
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


def get_feature_class(name):
    name_lower = name.lower()
    if 'polygon' in name_lower:
        return models.PolygonFeature
    if 'linestring' in name_lower:
        return models.LineFeature
    if 'point' in name_lower:
        return models.PointFeature
    raise KeyError('DAS Feature class not found for {0}'.format(name))


def make_external_id(layer, feature, id_field, name_field):
    name_value = ''
    id_value = ''
    for name in feature.fields:
        if id_field and name.lower() == id_field.lower():
            id_value = str(feature[name].value)
        elif name_field and name.lower() == name_field.lower():
            name_value = str(feature[name].value)
    return '-'.join((layer.name, name_value, id_value))


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


def contains_unique_keys_in_layer(layer, id_field, name_field):
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


def import_layer(layer, source_name, spatialfile_id, featuretype, featureset, presentation, featuretype_label, id_field, name_field):

    logger.info('Importing layer: %s, type: %s, fields: %s',
                layer.name, layer.geom_type, layer.fields)

    has_unique_keys = contains_unique_keys_in_layer(layer, id_field, name_field)

    for i, feature in enumerate(layer):

        if presentation:
            # TODO: get sft regardless of presentation and pass on further
            spatial_feature_type = get_spatial_feature_type(feature, featuretype_label, featuretype)
            if not spatial_feature_type:
                logger.warning('Did not get spatialfeaturetype for %s. Skipping', str(feature))
                continue
            spatial_feature_type.presentation = presentation
            # TODO: does a write in each iteration. Optimize.
            spatial_feature_type.save()

        # can optionally filter features based on Park attribute.
        # e.g., AP has features for multiple parks in the same feature layer
        # TODO: make configurable, move out filter key (e.g., Park below) & filter value (ui_site_url) to the admin UI.
        if hasattr(settings, 'UI_SITE_URL') and 'Park' in feature.fields:
            if feature['Park'].value.lower() in settings.UI_SITE_URL.lower():
                load_layer(layer, featuretype, featureset, feature, has_unique_keys, i, id_field, name_field, spatialfile_id, featuretype_label, source_name)
        else:
            load_layer(layer, featuretype, featureset, feature, has_unique_keys, i, id_field, name_field, spatialfile_id, featuretype_label, source_name)


def load_layer(layer, featuretype, featureset, feature, has_unique_keys, i, id_field, name_field, spatialfile_id, featuretype_label, source_name):
    external_id = make_external_id(layer, feature, id_field, name_field)
    if not has_unique_keys:
        external_id = external_id + '-' + str(i)
    if featureset:
        mappingv1_save_spatial_data(
            feature, featureset, featuretype, external_id, name_field, spatialfile_id)
    else:
        mappingv2_save_spatial_data(feature, featuretype, source_name,
                                    spatialfile_id, external_id, featuretype_label)


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
    geometry_mapper = GeometryMapper()
    
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
    feature_record = save_spatial_file(spatialfile_id, models.SpatialFile, feature_record)
    feature_record.save()


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


def import_feature_types(datasource, source_name, spatialfile_id):
    model = models.SpatialFeatureType
    for feature in datasource:
        fields = list(fields_iter(feature))
        global_id = feature['globalid'].value
        name = feature['type'].value

        provenance = {feature_name: feature[feature_name].value for feature_name in fields if feature_name in TYPE_PROVENANCE_FIELDS}
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

        try:
            type_record, created = model.objects.get_or_create(
                name=name,
                defaults=defaults,
                display_category=get_display_category(
                    feature['display_category'].value),
                external_id=global_id)
        except IntegrityError as err:
            logger.warning(err)
            return
        except Exception as error:
            raise ValidationError({'feature_types_file': ["Unable to process file: ", error]})

        logger.debug('Import feature_type: %s, created:%s',
                        global_id, created)

        if 'tags' in fields:
            type_record.tags = [value.strip()
                                for value in feature['tags'].value.split(',')]
        type_record.display_category = get_display_category(
            feature['display_category'].value)
        type_record.name = name
        for key, value in defaults.items():
            setattr(type_record, key, value)

        type_record.save()
