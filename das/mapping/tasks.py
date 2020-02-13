from arcgis.gis import GIS

from celery_once import QueueOnce
from das_server import celery
from mapping.models import ArcgisConfiguration
from mapping.utils import download_features_from_wfs


@celery.app.task(base=QueueOnce, once={'graceful': True})
def automate_download_features_from_wfs():
	feature_services = models.ArcgisConfiguration.objects.all()
	for obj in feature_services:
		# wsf connection
		gis = GIS(obj.service_url, username=obj.username, password=obj.password)
		saved_groups = models.ArcgisGroup.objects.filter(user=obj.username)
		
		for group in saved_groups:
			wfs_group = gis.groups.get(group.group_id)

			# download features
			download_features_from_wfs(None, obj, wfs_group)
