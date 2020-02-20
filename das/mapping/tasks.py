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
        background_download_features_from_wfs.apply_async(args=(obj.id,))


@celery.app.task(base=QueueOnce, once={'graceful': True})
def background_download_features_from_wfs(obj_id):
    # Task only accepts primitive data, acess config objects using obj_id
    obj, wfs_group = get_wfs_config_objects(obj_id)
    errored_files, success_files, group_members = [], [], wfs_group.content()

    for member in group_members:
        if member.type == "Feature Service":
            title = member.title.replace(' ', '-')
            logger.info(f'processing {title}')
            success_files, errored_files = utils.extract_gis_data(
                obj, member, title, errored_files, success_files)
    
    # update last download time
    obj.last_download = convert_date_string(str(datetime.now()))
    obj.save()

    utils.wfs_download_return_messages(None, errored_files, success_files)


def get_wfs_config_objects(obj_id):
    obj = models.ArcgisConfiguration.objects.get(id=obj_id)
    gis = utils.arcgis_authentication(None, obj)
    wfs_group = gis.groups.get(obj.groups.group_id)

    return obj, wfs_group
