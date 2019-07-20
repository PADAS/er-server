import json
import logging

import requests
from rest_framework import status

from das_server import celery
from sensors.gfw_alert_handler import GFWAlertHandler

logger = logging.getLogger(__name__)


@celery.app.task()
def download_gfw_alerts(download_url, common_event_fields, user_id):
    try:
        logger.debug(f'downloading from: {download_url}')
        rsp = requests.get(url=download_url, timeout=(2, 5))
    except Exception as ex:
        logger.warning('Exception occurred while downloading alert data. Ignoring')
        logger.exception(ex)

    else:
        if rsp and rsp.status_code == status.HTTP_200_OK:
            payload = json.loads(rsp.text)['data']

            errors = [GFWAlertHandler.create_event_from_downloadedalert(alert, common_event_fields, user_id)
                      for alert in payload]
            errors = filter(lambda x: len(list(x)) > 0, errors)

            if len(list(errors)) > 0:
                logger.warning(f'Errors processing downloaded alerts. {errors}')
