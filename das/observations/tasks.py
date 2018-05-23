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


# @celery.app.task(base=QueueOnce, once={'graceful': True, })
# def update_subject_status(subject_id):
#     logger.info(
#         'Celery worker handling new observation. subject_id=%s', subject_id)
#     observation = Observation.objects.get(id=instance.id)
#
#     logger.debug('handling Observation.post_save')
#     for delay_hours in VIEW_END_WINDOWS:
#         SubjectStatus.objects.update_from_observation(
#             observation, delay_hours=delay_hours[1] * 24)
