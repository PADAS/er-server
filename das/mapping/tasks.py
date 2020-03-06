import logging
from datetime import datetime, timezone

from celery_once import QueueOnce
from django.db import transaction

from das_server import celery
from mapping import models, esri_integration
from observations.utils import convert_date_string

logger = logging.getLogger(__name__)


@celery.app.task(base=QueueOnce, once={'graceful': True})
def automate_download_features_from_wfs():
    feature_services = models.ArcgisConfiguration.objects.filter(
        groups__isnull=False)
    for obj in feature_services:
        background_download_features_from_wfs.apply_async(args=(obj.id,))


@celery.app.task(base=QueueOnce, once={'graceful': True})
def background_download_features_from_wfs(obj_id):
    # Task only accepts primitive data, acess config objects using obj_id
    arc_config, wfs_group = get_wfs_config_objects(obj_id)
    errored_files, success_files, group_members = [], [], wfs_group.content()
    items_to_download = None
    AP_GROUP_ID = 'a47fb09a85fb41ec9d70ef608761f7fa'
    ER_GROUP_ID = 'dc27285af43546a080407241d7eeab47'

    # restricting APN group members for demo
    if wfs_group.id == AP_GROUP_ID:
        items_to_download = [
            'Akagera_Land_Cover',
            'Built_point',
            'Hydrology_polygon',
            # 'Transport_line',
            # 'Hydrology_line'
        ]
    elif wfs_group.id == ER_GROUP_ID:
        items_to_download = [
            'Point features near Vulcan',
            'STE Points Wells Closed',
            'polygon features',
            'Lines near Vulcan',
            'Villages'
        ]
    received_item_ids = [m.itemid for m in group_members]
    delete_result = models.ArcgisItem.objects.filter(arcgis_config=arc_config).exclude(
        id__in=received_item_ids).delete()
    logger.info(f'deleted items {delete_result}')
    for member in group_members:
        try:
            with transaction.atomic():
                if member.type == "Feature Service":
                    # TODO: before merge to develop remove all the items_to_download related stuff
                    if items_to_download and member.title not in items_to_download:
                        logger.info(f'Skipping {member.title}')
                        continue
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
                    esri_integration.extract_gis_data(arc_config, member, title, errored_files, success_files, arcgis_item.id)
                    # arcgis_item.save()  # update model's updated_at field

        except Exception as ex:
            logger.warning(f'Exception raised for object id {obj_id}')
            logger.exception(ex)

    # update last download time
    arc_config.last_download = convert_date_string(str(datetime.now()))
    arc_config.save()

    esri_integration.wfs_download_return_messages(None, errored_files, success_files)


def get_wfs_config_objects(obj_id):
    obj = models.ArcgisConfiguration.objects.get(id=obj_id)
    gis = esri_integration.arcgis_authentication(None, obj)
    wfs_group = gis.groups.get(obj.groups.group_id)

    return obj, wfs_group
