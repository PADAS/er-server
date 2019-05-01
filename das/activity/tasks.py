import logging

from versatileimagefield.image_warmer import VersatileImageFieldWarmer
from das_server import celery
from activity.models import EventPhoto, Event

from activity.alertingservice import evaluate_event

logger = logging.getLogger(__name__)


@celery.app.task(bind=True)
def evaluate_alert_rules(self, event_id):

    try:
        logger.info('Evaluating Event %s for alerting.', event_id)
        event = Event.objects.get(id=event_id)
        action_list = evaluate_event(event)

        print(f'Action List: {action_list}')
    except Exception as e:
        logger.exception('Failed when evaluating alert rules for event {}'.format(event_id))


@celery.app.task(bind=True)
def warm_eventphotos(self, event_photo_id):

    try:
        logger.info('Warming images for event_photo_id=%s', event_photo_id)
        instance = EventPhoto.objects.get(id=event_photo_id)
        warmer = VersatileImageFieldWarmer(
            instance_or_queryset=instance,
            rendition_key_set='event_photo',
            image_attr='image'
        )
        num_created, failed_to_create = warmer.warm()
        logger.info('Warmed images for event_photo_id=%s', event_photo_id)
    except Exception as e:
        logger.exception('Failed when warming images for event_photo_id {}'.format(event_photo_id))

