import logging

import json

from django.template.loader import render_to_string
from activity.models import EventPhoto, Event, EventType, NotificationMethod, AlertRule
from das_server import celery, mailer
from reports.distribution import send_report
from activity.alerting.businessrules import render_event

logger = logging.getLogger(__name__)


def send_event_alert(alert_rule_id=None, event_id=None, notification_method_id=None):
    '''
    Resolve the necessary objects for sending an alert.
    :param alert_rule_id:
    :param event_id:
    :param notification_method_id:
    :return:
    '''
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

    report_context = render_event_alert_context(alert_rule, event, notification_method)

    print(json.dumps(report_context, indent=2, default=str))
    email_body = render_to_string('eventalert.html', report_context)

    if notification_method.method == 'email':
        logger.debug(f"Sending email alert {event_id} to {notification_method.value}")
        send_report(
            subject=report_context['message_subject'],
            to_email=notification_method.value,
            html_content=email_body,
            text_content=f'EarthRanger Alert (attached as HTML).'
        )
        logger.info(f"Sent email alert {event_id} to {notification_method.value}")
    elif notification_method.method.lower() == 'sms':
        logger.debug(f"Sending sms alert {event_id} to {notification_method.value}")
        parameters = {
            'serial': event.id,
            'color': 'gray',
            'title': event.title
        }
        msg = render_to_string('new_event_sms.txt', parameters).strip()
        mailer.send_sms(msg, notification_method.value)
        logger.info(f"Sent sms alert {event_id} to {notification_method.value}")
    else:
        logger.error(f"Unsupported NotifcationMethod ({notification_method.method})"
                     f" when processing event:{event_id} for notification: {notification_method.id}")


def render_event_alert_context(alert_rule, event, notification_method):
    '''
    Render an alert context for the given parameters. Assume that the parameters are
    valid and that permissions have been respected.
    :param alert_rule: The alert rule that indicated the message.
    :param event:
    :param notification_method: The method for sending the alert.
    :return: A dict containing the alert context.
    '''
    eventdata = render_event(event, notification_method.owner)

    eventdata['title'] = eventdata['title'] or event.title

    logger.debug('Rendered event: %s', json.dumps(eventdata, indent=2, default=str))

    report_context = {
        'message_subject': create_email_subject(event),
        'alert_rule': alert_rule.title,
        'event': {
            'time': event.event_time,
            'priority': event.priority_label,
            'title': eventdata['title'],
            'details': eventdata['event_details'],
        }
    }

    return report_context


def create_email_subject(event):
    priority = event.priority_label
    title = event.title or event.event_type.display
    # if title is None:
    #     event_type = EventType.objects.get(id=event.event_type_id)
    #     title = event_type.display

    return f"EarthRanger {priority} Alert: [{event.serial_number}] {title}"
