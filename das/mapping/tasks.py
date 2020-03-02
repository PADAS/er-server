import logging
from datetime import datetime

from celery_once import QueueOnce

from das_server import celery
from mapping import models, utils
from observations.utils import convert_date_string

logger = logging.getLogger(__name__)


@celery.app.task(base=QueueOnce, once={'graceful': True})
def automate_download_features_from_wfs():
    feature_services = models.ArcgisConfiguration.objects.filter(
        groups__isnull=False)
    for obj in feature_services:
        load_features_from_wfs.apply_async(args=(obj.id, obj.groups.group_id))


@celery.app.task(base=QueueOnce, once={'graceful': True})
def load_features_from_wfs(obj_id, group_id):
    # Task only accepts primitive data, access config objects using obj_id
    obj, wfs_group = get_wfs_config_objects(obj_id, group_id)
    errored_files, success_files, group_members = [], [], wfs_group.content()

    # items_to_download = None
    # AP_GROUP_ID = 'a47fb09a85fb41ec9d70ef608761f7fa'
    # ER_GROUP_ID = 'dc27285af43546a080407241d7eeab47'
    #
    # # restricting APN group members for demo
    # if wfs_group.id == AP_GROUP_ID:
    #     items_to_download = [
    #         'Akagera_Land_Cover',
    #         'Built_point',
    #         'Hydrology_polygon',
    #         'Transport_line',
    #         # 'Hydrology_line'
    #     ]
    # elif wfs_group.id == ER_GROUP_ID:
    #     items_to_download = [
    #         'Point features near Vulcan',
    #         'STE Points Wells Closed',
    #         'polygon features',
    #         'Lines near Vulcan',
    #         'Villages'
    #     ]

    for member in group_members:
        if member.type == "Feature Service":
            # TODO: before merge to develop remove all the items_to_download related stuff
            # if items_to_download and member.title not in items_to_download:
            #     logger.info(f'Skipping {member.title}')
            #     continue
            title = member.title.replace(' ', '-')
            logger.info(f'processing {title}')
            success_files, errored_files = utils.extract_gis_data(
                obj, member, title, errored_files, success_files)

    # update last download time
    obj.last_download = convert_date_string(str(datetime.now()))
    obj.save()

    utils.wfs_download_return_messages(None, errored_files, success_files)


def get_wfs_config_objects(obj_id, group_id):
    obj = models.ArcgisConfiguration.objects.get(id=obj_id)
    gis = utils.arcgis_authentication(None, obj)
    wfs_group = gis.groups.get(group_id)

    return obj, wfs_group

# todo: cleanup when merging with esri work
@celery.app.task(base=QueueOnce, once={'graceful': True})
def load_spatial_features_from_files(data_files, tmpdirs, source_name, spatialfile_id, feature_types_file=None,
                                     layer=None, presentation=None, featuretype_label=None,
                                     id_field=None, name_field=None, featuretype=None, featureset=None):

    model = models.SpatialFile if featureset else models.SpatialFeatureFile
    spatial_file = model.objects.filter(id=spatialfile_id)

    try:
        extract_features(data_files, source_name, spatial_file, tmpdirs, feature_types_file, presentation, featuretype_label, featureset)
        spatial_file.update(status='Success')
    except Exception as ex:
        logger.exception(ex)
        spatial_file.update(status=f'Error: {ex}')
    finally:
        datasource = None


def extract_features(data_files, source_name, spatialfile, tmpdirs=[], feature_types_file=None, presentation=None, featuretype_label=None, featureset=None):
    data_files = [data_files] if isinstance(
        data_files, str) else data_files
    if feature_types_file:
        datasource, layer_num = utils.get_datasource_and_layer_num(
            feature_types_file, tmpdirs, 0)
        utils.import_feature_types(
            datasource[layer_num], source_name)

    for filename in data_files:
        datasource, layer_num = utils.get_datasource_and_layer_num(
            filename, tmpdirs, spatialfile.layer_number)
        featuretype = spatialfile.feature_type.name if spatialfile.feature_type else None
        utils.import_layer(
            datasource[layer_num], source_name, spatialfile.id,
            featuretype, featureset, presentation, featuretype_label,
            spatialfile.id_field, spatialfile.name_field)
        utils.cleanup_files(filename)