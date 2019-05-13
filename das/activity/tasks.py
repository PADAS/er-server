import logging

from celery_once import QueueOnce

from versatileimagefield.image_warmer import VersatileImageFieldWarmer
from django.template.loader import render_to_string
from activity.alerting.service import evaluate_event
from activity.alerting.message import send_event_alert

from activity.models import EventPhoto, Event, EventType, NotificationMethod, AlertRule
from das_server import celery, mailer
from reports.distribution import send_report
from activity.alerting.businessrules import render_event

logger = logging.getLogger(__name__)


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


@celery.app.task(bind=True)
def evaluate_alert_rules(self, event_id):

    try:
        logger.info('Evaluating Event %s for alerting.', event_id)
        event = Event.objects.get(id=event_id)
        action_list = evaluate_event(event)

        # For a single event we've gotten the list of alert rules that match.
        # Now we can iterate over them to accumulate the notification methods that should be targeted.

        # Resolve distinct list of active NotificationMethod objects for the given set of alert rule IDs.
        # TODO: revisit ordering by alert-rule to preserve precedencce
        alert_rule_ids = [action['alert_rule_id'] for action in action_list]

        already_queued_nids = set() # accumulator for Notification Methods.
        for alert_rule in AlertRule.objects.filter(id__in=alert_rule_ids).order_by('ordernum', 'title'):
            for notification_method in alert_rule.notification_methods.filter(is_active=True):

                if notification_method.id not in already_queued_nids:
                    kwargs = {
                        'alert_rule_id': str(alert_rule.id),
                        'event_id': str(event_id),
                        'notification_method_id': str(notification_method.id)
                    }

                    send_alert_to_notificationmethod.apply_async(args=(), kwargs=kwargs)
                already_queued_nids.add(notification_method.id)

    except Exception as e:
        logger.exception('Failed when evaluating alert rules for event {}'.format(event_id))


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def send_alert_to_notificationmethod(alert_rule_id=None, event_id=None, notification_method_id=None):

    if any((x is None for x in (alert_rule_id, notification_method_id, event_id))):
        raise ValueError('Coding error.  I need keyword arguments.')

    logger.info(f"Sending alert of event {event_id} to notification id {notification_method_id}")
    send_event_alert(alert_rule_id=alert_rule_id, event_id=event_id, notification_method_id=notification_method_id)

