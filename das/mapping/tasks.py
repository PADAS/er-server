from arcgis.gis import GIS

from celery_once import QueueOnce
from das_server import celery
from mapping.models import ArcgisConfiguration
from mapping.utils import download_features_from_wfs


@celery.app.task(base=QueueOnce, once={'graceful': True})
def automate_download_features_from_wfs():
    feature_services = ArcgisConfiguration.objects.all()
    for wfs in feature_services:
        # wsf connection
        gis = GIS(wfs.service_url, username=wfs.username, password=wfs.password)
        group = gis.groups.get(wfs.group_id)

        # download features
        download_features_from_wfs(None, group, wfs)
