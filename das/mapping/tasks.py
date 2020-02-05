import logging
import os

from arcgis.gis import GIS
from celery_once import QueueOnce
from django.core import management

from das_server import celery
from mapping.models import ArcgisConfiguration

logger = logging.getLogger(__name__)


@celery.app.task(base=QueueOnce, once={'graceful': True})
def download_features_from_wfs():
    feature_services = ArcgisConfiguration.objects.all()
    for wfs in feature_services:
        gis = GIS(wfs.service_url, username=wfs.username, password=wfs.password)
        group = gis.groups.get(wfs.group_id)

        items_for_demo = ['Built_point']
        group_members, errored_files, success_files, data = group.content(), [], [], None
        for member in group_members:
            if member.type == "Feature Service" and member.title in items_for_demo:
                title = member.title.replace(' ', '-')
                logger.info(f'processing {title}')
                try:
                    data = member.layers[0].query().to_geojson
                    file_ext = 'geojson'
                except KeyError:
                    data = member.layers[0].query().to_json
                    file_ext = 'json'
                except Exception as error:
                    logger.info(f'Error reading from {member.title}', error)
                    errored_files.append(member.title)
                if data:
                    with open(f'./{title}.{file_ext}', 'w') as data_file:
                        data_file.write(data)
                        management.call_command(
                            'importlayer', 'importspatialfile', data_file.name,
                            source=wfs.source, name_field=wfs.name_field, id_field=wfs.id_field
                        )
                        os.remove(data_file.name)
                        success_files.append(member.title)
        if len(errored_files) > 0:
            logger.error(f"Could not read data from {len(errored_files)} file(s): {', '.join(errored_files)}")

        if len(success_files) > 0:
            logger.error(f'Features Successfully loaded into ER from {len(success_files)} file(s)')
