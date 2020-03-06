import logging
from datetime import datetime, timezone

from celery_once import QueueOnce
from django.db import transaction

from das_server import celery
from mapping import models, utils
from mapping.esri_integration import arcgis_authentication, wfs_download_return_messages, extract_gis_data
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
    arc_config, wfs_group = get_wfs_config_objects(obj_id, group_id)
    errored_files, success_files, group_members = [], [], wfs_group.content()

    received_item_ids = [m.itemid for m in group_members]
    delete_result = models.ArcgisItem.objects.filter(arcgis_config=arc_config).exclude(
        id__in=received_item_ids).delete()
    logger.info(f'deleted items {delete_result}')
    for member in group_members:
        try:
            with transaction.atomic():
                if member.type == "Feature Service":
                    title = member.title.replace(' ', '-')
                    last_modified = datetime.fromtimestamp(int(member.modified/1000), timezone.utc)
                    logger.info(f'processing {title}')
                    arcgis_item, created = models.ArcgisItem.objects.get_or_create(
                        id=member.id,
                        name=title,
                        arcgis_config=arc_config
                    )
                    # timestamps seem broken in arcgis
                    # if created or last_modified > arcgis_item.updated_at:
                    extract_gis_data(arc_config, member, title, errored_files, success_files, arcgis_item.id)
                    # arcgis_item.save()  # update model's updated_at field

        except Exception as ex:
            logger.warning(f'Exception raised for object id {obj_id}')
            logger.exception(ex)

    # update last download time
    arc_config.last_download = convert_date_string(str(datetime.now()))
    arc_config.save()

    wfs_download_return_messages(None, errored_files, success_files)


def get_wfs_config_objects(obj_id, group_id):
    obj = models.ArcgisConfiguration.objects.get(id=obj_id)
    gis = arcgis_authentication(None, obj)
    wfs_group = gis.groups.get(group_id)

    return obj, wfs_group


@celery.app.task(base=QueueOnce, once={'graceful': True})
def load_spatial_features_from_files(data_files, tmpdirs, source_name, spatialfile_id, feature_types_file=None,
                                     layer=None, id_field=None, name_field=None, featuretype=None, featureset=None):
    model = models.SpatialFile if featureset else models.SpatialFeatureFile
    spatial_file = model.objects.filter(id=spatialfile_id)

    try:
        extract_features_from_files(data_files, source_name, spatial_file[0], feature_types_file, layer, presentation,
                                    featuretype_label, id_field, name_field, featuretype, featureset, tmpdirs)
        spatial_file.update(status='Success')
    except Exception as ex:
        logger.exception(ex)
        spatial_file.update(status=f'Error: {ex}')
    finally:
        datasource = None


def extract_features_from_files(data_files, source_name, spatial_file, feature_types_file=None, layer=None,
                                presentation=None, featuretype_label=None, id_field=None, name_field=None,
                                featuretype=None, featureset=None, tmpdirs=None):
    data_files = [data_files] if isinstance(
        data_files, str) else data_files
    if feature_types_file:
        datasource, layer_num = utils.get_datasource_and_layer_num(
            feature_types_file, tmpdirs, 0)
        utils.import_feature_types(
            datasource[layer_num], source_name)

    for filename in data_files:
        datasource, layer_num = utils.get_datasource_and_layer_num(
            filename, tmpdirs, layer)
        file_id = spatial_file.id if spatial_file else None
        utils.import_layer(
            datasource[layer_num], source_name, file_id,
            featuretype, featureset, presentation, featuretype_label,
            id_field, name_field)
        utils.cleanup_files(filename, spatial_file)
