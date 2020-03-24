import logging
from datetime import datetime, timezone

from celery_once import QueueOnce
from django.core.files.storage import default_storage
from django.db import transaction

from das_server import celery
from mapping import models, spatialfile_utils, utils
from mapping.esri_integration import (arcgis_authentication, extract_gis_data,
                                      wfs_download_return_messages)
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
def load_spatial_features_from_files(spatialfile_id):
    model = models.SpatialFeatureFile if utils.MAPPING_FEATURES_V2 else models.SpatialFile
    spatial_file = model.objects.filter(id=spatialfile_id)

    if spatial_file.exists():
        try:
            spatialfile_utils.extract_features_from_files(spatial_file[0], model)
            spatial_file.update(status='Success')
        except Exception as ex:
            logger.exception(ex)
            spatial_file.update(status=f'Error: {ex}')
    else:
        logger.exception(f'Spatialfile with id {spatialfile_id} does not exist')

    utils.cleanup_files()
