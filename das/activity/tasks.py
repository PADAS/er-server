import logging

from celery_once import QueueOnce

from versatileimagefield.image_warmer import VersatileImageFieldWarmer
from django.template.loader import render_to_string
from activity.alertingservice import evaluate_event
from activity.models import EventPhoto, Event, EventType, NotificationMethod, AlertRule
from das_server import celery, mailer, settings
from reports.distribution import send_report

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
        # notification_methods = NotificationMethod.objects.filter(is_active=True,
        #                                   alert_rule__in=AlertRule.objects.filter(id__in=alert_rule_ids)) \
        #     .distinct('id').annotate(alert_rule_id=F('alert_rule__id'))

        already_queued_nids = set() # accumulator for Notification Methods.
        for alert_rule in AlertRule.objects.filter(id__in=alert_rule_ids).order_by('ordernum', 'title'):
            for notification_method in alert_rule.notification_methods.filter(is_active=True):

                if notification_method.id not in already_queued_nids:
                    kwargs = {
                        'alert_rule_id': str(alert_rule.id),
                        'event_id': str(event_id),
                        'notification_method_id': str(notification_method.id)
                    }

                    send_alert_to_user.apply_async(args=(), kwargs=kwargs)
                already_queued_nids.add(notification_method.id)

    except Exception as e:
        logger.exception('Failed when evaluating alert rules for event {}'.format(event_id))


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def send_alert_to_user(alert_rule_id=None, event_id=None, notification_method_id=None):

    if any((x is None for x in (alert_rule_id, notification_method_id, event_id))):
        raise ValueError('Coding error.  I need keyword arguments.')

    # At this point we have IDs for the alert-rule, the notification-method and the event.
    # We can render the event message
    #   and also include the "reason" (ex. the Alert Rule Title)

    logger.info(f"Sending alert of event {event_id} to notification id {notification_method_id}")

    event, notification_method, alert_rule = None, None, None
    try:
        event = Event.objects.get(id=event_id)
        notification_method = NotificationMethod.objects.get(id=notification_method_id)
        alert_rule = AlertRule.objects.get(id=alert_rule_id)
    except Event.DoesNotExist:
        logger.exception(f'No Event found for id: {event_id}')
    except NotificationMethod.DoesNotExist:
        logger.exception(f'No NotificationMethod found for id: {notification_method_id}')
    except AlertRule.DoesNotExist:
        logger.exception(f'No AlertRule found for id: {alert_rule_id}')

    if any((x is None for x in [event, notification_method, alert_rule])):
        raise ValueError(f'Cannot continue with event={event}, '
                         f'alert_rule={alert_rule}, notification_method={notification_method}')

    recip = notification_method.value
    method = notification_method.method
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
            'color': 'gray',
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
