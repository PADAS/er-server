import logging
import json

from celery_once import QueueOnce
from das_server import celery, pubsub
from observations import servicesutils

logger = logging.getLogger(__name__)


@celery.app.task()
def store_and_forward_service_status(service_name=None, data=None):

    data = data or {}
    servicesutils.store_service_status(service_name=service_name, data=data)
    # Call broadcast (if it's not already in the queue)
    broadcast_service_status.apply_async()
