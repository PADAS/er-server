import logging

from versatileimagefield.image_warmer import VersatileImageFieldWarmer
from django.template.loader import render_to_string
from activity.alertingservice import evaluate_event
from activity.models import EventPhoto, Event, EventType, NotificationMethod
from das_server import celery, mailer, settings
from reports.distribution import send_report

logger = logging.getLogger(__name__)


@celery.app.task(bind=True)
def evaluate_alert_rules(self, event_id):

    try:
        logger.info('Evaluating Event %s for alerting.', event_id)
        event = Event.objects.get(id=event_id)
        action_list = evaluate_event(event)
        #send_alert_to_user.delay((event.id, notification_id))
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


# apparently a tuple is needed for the passing parameters to a subtask and delay()
@celery.app.task(bind=True)
def send_alert_to_user(self, payload):
    (event_id, notif_id) = payload
    logger.info(f"Sending alert of event {event_id} to notification id {notif_id}")
    event = Event.objects.get(id=event_id)
    notification = NotificationMethod.objects.get(id=notif_id)
    recip = notification.value
    method = notification.method
    subject = create_email_subject(event)
    if method.lower() == 'email':
        send_report(
            subject=subject,
            to_email=recip,
            text_content=str(event.__dict__)
        )
        logger.info(f"Sent email alert {event_id} to {recip}")
    elif method.lower() == 'sms':
        parameters = {
            'serial': event.id,
            'color': priority,
            'title': event.title
        }
        msg = render_to_string('new_event_sms.txt', parameters).strip()
        mailer.send_sms(msg, recip)
        logger.info(f"Sent sms alert {event_id} to {recip}")
    else:
        logger.error(f"Failed to send alert {event_id} to {recip} via {method}")


# TODO - move me to a good location
def create_email_subject(event):
    priority = event.get_display_value('priority', 'Grey')
    title = event.title
    if title is None:
        etype = EventType.objects.get(id=event.event_type_id)
        title = etype.display

    return f"DAS {priority} Alert: {event.serial_number} {title}"
