import datetime
import logging
import tempfile

import arcgis
from django.conf import settings
from django.contrib import messages
from django.contrib.gis.gdal import GDALException
from django.core import management
from django.utils.safestring import mark_safe

from arcgis2geojson import arcgis2geojson
from mapping import models
from mapping.utils import (contains_unique_keys_in_layer, geometry_mapper,
                           get_datasource_and_layer_num, get_or_create_feature,
                           get_spatial_feature_type, make_external_id,
                           set_feature_name)

logger = logging.getLogger(__name__)

ESRI_FEATURE_EDITDATE = 'EditDate'
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

message = messages.add_message


def arcgis_integration(request, obj):
    from mapping.tasks import load_features_from_wfs
    gis = arcgis_authentication(request, obj)
    if gis:
        acrgis_groups_found = search_groups(gis, obj)
        if "_testconnection" in request.POST:
            message(request, messages.INFO, f'Successful Configuration')
        elif "_downloadfeatures" in request.POST:
            # set to a background task
            if obj.groups:
                task_started_msg = "Features download in progress, checkout loaded <a href='/admin/mapping/spatialfeature/'>spatialfeatures</a> after a few minutes"
                message(request, messages.INFO, mark_safe(task_started_msg))
                load_features_from_wfs.apply_async(args=(obj.id, obj.groups.group_id))
                # load_features_from_wfs(obj.id, obj.groups.group_id)
            else:
                error_msg = "Select a group to enable features download"
                message(request, messages.ERROR, error_msg) if request else logger.debug(error_msg)
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


def extract_gis_data(obj, member, title, errored_files, success_files, arcgis_item_id):
    data = None
    simple_presentation = None
    try:
        # Not handling multiple layers just yet.
        simple_presentation = import_featuretype_presentation(member.layers[0].properties.drawingInfo.renderer)
        # set the spatial reference to 4326 in the query
        data = member.layers[0].query(out_sr=4326).to_geojson
    except KeyError:
        logger.debug('to_geojson failed, trying to_json')
        data = arcgis2geojson(member.layers[0].query().to_json)
    except Exception as error:
        logger.info(f'Error reading from {member.title}', error)
        errored_files.append(member.title)
    if data:
        # TODO: validate that we have valid, non-empty content in data, else gdal barfs later
        success_files = extract_features(obj, member, title, data, success_files, simple_presentation, arcgis_item_id)
        return success_files, errored_files


def extract_features(obj, member, title, data, success_files, simple_presentation, arcgis_item_id):
    with tempfile.NamedTemporaryFile() as data_file:
        data_file.write(data.encode())
        data_file.flush()
        data_file.seek(0)
        import_features_from_esri(tmp_filename=data_file.name, arcgis_item_id=arcgis_item_id,
                                  external_sourcename=obj.source, type_field=obj.type_label, id_field=obj.id_field,
                                  name_field=obj.name_field, simple_presentation=simple_presentation, )
        success_files.append(member.title)
        return success_files


def import_features_from_esri(tmp_filename, arcgis_item_id, external_sourcename, type_field, id_field, name_field,
                              simple_presentation):
    logger.info('Importing esri features for itemid %s from temp file: %s', arcgis_item_id, tmp_filename)
    # comeback cleanup
    try:
        datasource, layer_num = get_datasource_and_layer_num(filename=tmp_filename)
        layer = datasource[layer_num]

        arc_item = models.ArcgisItem.objects.get(id=arcgis_item_id)
        # TODO: bail if arc_item is null

        # TODO: revisit and handle case where layer/features do not have a GlobalID
        received_global_ids = [make_external_id(layer, f, id_field, name_field, arc_item.id) for f in layer]
        delete_result = models.SpatialFeature.objects.filter(arcgis_item=arc_item).exclude(
            external_id__in=received_global_ids).delete()
        logger.info(f'deleted features {delete_result}')

        has_unique_keys = contains_unique_keys_in_layer(id_field, name_field, layer)
        for i, feature in enumerate(layer):

            if simple_presentation:
                spatial_feature_type = get_spatial_feature_type(feature, type_field)
                if not spatial_feature_type:
                    logger.warning('Did not get or create spatialfeaturetype for %s. Skipping', str(feature))
                    continue
                spatial_feature_type.presentation = simple_presentation
                # TODO: does a write in each iteration. Optimize.
                spatial_feature_type.save()

            # linked to above to revisit if don't have a GlobalID
            external_id = make_external_id(layer, feature, id_field, name_field, arc_item.id)
            if not has_unique_keys:
                external_id = external_id + '-' + str(i)

            # can optionally filter features based on Park attribute.
            # e.g., AP has features for multiple parks in the same feature layer
            # TODO: make configurable, move out filter key (e.g., Park below) & filter value (ui_site_url)
            #  to the admin UI.
            if hasattr(settings, 'UI_SITE_URL') and 'Park' in feature.fields:
                if feature['Park'].value.lower() in settings.UI_SITE_URL.lower():
                    save_esri_feature(feature, external_sourcename, external_id, type_field, arc_item, i)
            else:
                save_esri_feature(feature, external_sourcename, external_id, type_field, arc_item, i)
    finally:
        datasource = None


def db_feature_needs_update(feature_record, feature):
    needs_update = True
    if feature_record and ESRI_FEATURE_EDITDATE in feature.fields:
        last_edit_ts = int(feature.get(ESRI_FEATURE_EDITDATE))
        last_edit_at = datetime.datetime.fromtimestamp(int(last_edit_ts/1000), datetime.timezone.utc)
        needs_update = last_edit_at > feature_record.updated_at

    return needs_update


def save_esri_feature(feature, source_name, external_id, type_label, arcgis_item, counter):
    # With Esri integration we've seen some feature services give us json that has features with "geometry" missing
    # this handles and ignores that issue
    try:
        model_field_type = models.SpatialFeature._meta.get_field('feature_geometry')
        feature_geometry = geometry_mapper.get_db_geom(feature.geom, model_field_type)
    except GDALException as gex:
        logger.warning(f'Saving feature {external_id} raised GDALException: {gex}')
        return

    feature_type = get_spatial_feature_type(feature, type_label)
    if not feature_type:
        return

    feature_record, created = get_or_create_feature(external_id, dict(feature_geometry=feature_geometry,
                                                                      feature_type=feature_type))

    if not feature_record:
        return

    if created or db_feature_needs_update(feature_record, feature):
        logger.debug(f'creating or updating feature {external_id}')
        feature_record.arcgis_item = arcgis_item
        feature_record.external_source = source_name
        feature_record.feature_geometry = feature_geometry
        set_feature_name(feature_record, feature, feature_type, counter)
        feature_record.clean()
        feature_record.save()
    else:
        logger.debug(f'Skipping update for feature {external_id}')


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
