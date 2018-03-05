import logging
import json

from celery_once import QueueOnce
from das_server import celery, pubsub
from observations import servicesutils

logger = logging.getLogger(__name__)


@celery.app.task()
def store_and_forward_service_status(provider_key=None, data=None):

    data = data or {}
    servicesutils.store_service_status(provider_key=provider_key, data=data)
