import json
import logging
from datetime import datetime

import pytz
import sendsms.api

from django.conf import settings
from django.db.models import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from activity.alerting.businessrules import (infer_event_state, render_event,
                                             resolve_event_revisions)
from activity.models import (NOTIFICATION_METHOD_EMAIL,
                             NOTIFICATION_METHOD_SMS,
                             NOTIFICATION_METHOD_WHATSAPP, AlertRule, Event,
                             EventNotification, NotificationMethod)
from reports.distribution import send_report
from utils import schema_utils
from utils.whatsapp import send_whatsapp

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
        notification_method = NotificationMethod.objects.get(
            id=notification_method_id)
        alert_rule = AlertRule.objects.get(id=alert_rule_id)
    except Event.DoesNotExist:
        logger.exception(f'No Event found for id: {event_id}')
    except NotificationMethod.DoesNotExist:
        logger.exception(
            f'No NotificationMethod found for id: {notification_method_id}')
    except AlertRule.DoesNotExist:
        logger.exception(f'No AlertRule found for id: {alert_rule_id}')

    if any((x is None for x in [event, notification_method, alert_rule])):
        raise ValueError(f'Cannot continue with event={event}, '
                         f'alert_rule={alert_rule}, notification_method={notification_method}')

    # Get Revisions
    event_revision, details_revision = resolve_event_revisions(event)

    # Calculate updated fields
    updated_event_fields = get_revised_event_fields(event_revision)
    updated_event_details_fields = get_revised_event_details_fields(
        details_revision)

    if 'priority' in updated_event_fields:
        updated_event_fields['priority']['new'] = event.get_priority_display()
        updated_event_fields['priority']['old'] = Event(priority=updated_event_fields['priority']['old']) \
            .get_priority_display()

    report_context = render_event_alert_context(alert_rule, event, notification_method,
                                                event_revision=event_revision,
                                                event_updated_fields=updated_event_fields,
                                                event_details_updated_fields=updated_event_details_fields)

    if not report_context:
        logger.info(
            f'No report context for event {event.serial_number} and notification_method {notification_method_id}')
        return

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f'Report context: {json.dumps(report_context, indent=2, default=str)}')
        logger.debug(
            f'Update Event Fields: {json.dumps(updated_event_fields, indent=2, default=str)}')
        logger.debug(
            f'Update Event Details Fields: {json.dumps(updated_event_details_fields, indent=2, default=str)}')

    if notification_method.method == NOTIFICATION_METHOD_EMAIL:

        email_body = render_to_string('eventalert.html', report_context)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Sending email body: {email_body}')

        logger.debug(
            f"Sending email alert {event_id} to {notification_method.value}")
        send_report(
            subject=report_context['message_subject'],
            to_email=notification_method.value,
            html_content=email_body,
            text_content=f'EarthRanger Alert (attached as HTML).'
        )
        logger.info(
            f"Sent email alert {event_id} to {notification_method.value}")

        EventNotification.objects.create(event=event, method=notification_method.method,
                                         value=notification_method.value,
                                         owner=notification_method.owner)

    elif notification_method.method.lower() == NOTIFICATION_METHOD_SMS:
        logger.debug(
            f"Sending sms alert {event_id} to {notification_method.value}")
        sms_body = render_to_string('eventalert.sms', report_context)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Sending sms body: {sms_body}')

        sendsms.api.send_sms(body=sms_body, from_phone='',
                             to=[notification_method.value, ])
        logger.info(
            f"Sent sms alert {event_id} to {notification_method.value}")

        EventNotification.objects.create(event=event, method=notification_method.method,
                                         value=notification_method.value,
                                         owner=notification_method.owner)

    elif notification_method.method.lower() == NOTIFICATION_METHOD_WHATSAPP:
        logger.debug(
            f"Sending whatsapp alert {event_id} to {notification_method.value}")
        whatsapp_body = render_to_string('eventalert.whatsapp', report_context)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Sending sms body: {whatsapp_body}')

        to_number = "+" + notification_method.value if not notification_method.value.startswith(
            '+') else notification_method.value
        send_whatsapp(body=whatsapp_body, to=to_number)
        logger.info(f"Sent alert {event_id} to {notification_method.value}")

        EventNotification.objects.create(event=event, method=notification_method.method,
                                         value=notification_method.value,
                                         owner=notification_method.owner)

    else:
        logger.error(f"Unsupported NotifcationMethod ({notification_method.method})"
                     f" when processing event:{event_id} for notification: {notification_method.id}")


def get_revised_event_fields(event_revision):
    if not event_revision:
        return {}

    try:
        previous_version = event_revision.get_previous_by_revision_at(
            object_id=event_revision.object_id)
    except ObjectDoesNotExist:
        return {}
    else:
        current_data = event_revision.data
        previous_data = previous_version.data
        revision_changes = dict_changes(current_data, previous_data)
        return revision_changes


def get_revised_event_details_fields(event_details_revision):
    '''

    :param event_details_revision:
    :return:
    '''
    if not event_details_revision:
        return {}

    try:
        previous_version = event_details_revision.get_previous_by_revision_at(
            object_id=event_details_revision.object_id)
    except ObjectDoesNotExist:
        return {}
    else:
        current_data = event_details_revision.data['data'].get('event_details')
        previous_data = previous_version.data['data'].get('event_details')
        revision_changes = dict_changes(current_data, previous_data)
        return revision_changes


def dict_changes(current, previous, ignore_these=('sort_at', 'updated_at', 'created_at')):
    '''
    Given two dicts, determine which if any fields changed and report the change back in the form
    {
       'changed_key': {'old': <old-value>, 'new': <new-value' }
    }
    :param current:
    :param previous:
    :param ignore_these: a list of keys to ignore.
    :return:
    '''
    # delta = dict(set(current.items()) - set(previous.items()))
    # changes = dict((k, {'new': v, 'old': previous[k]}) for k, v in delta.items() if k not in ignore_these)

    changes = dict((k, {'new': v, 'old': previous.get(k)}) for k, v in current.items() if k not in ignore_these
                   and v != previous.get(k))
    return changes


priority_label_colors = {
    'Red': '#b00000',
    'Amber': '#d97900',
    'Green': '#00571c'
}

priority_label_color_default = '#3E4349'


def coerce_state_value(event=None, val=None):
    if event:
        val = infer_event_state(event)
    return _('Resolved') if val == 'resolved' else _('New') if val == 'new' else _('Active')


def render_pretty_value(internal_value):

    if isinstance(internal_value, dict):
        return internal_value.get('name')
    if isinstance(internal_value, (list, tuple)):
        return ', '.join(str(item.get('name')) for item in internal_value if 'name' in item)

    return str(internal_value)


def render_event_alert_context(alert_rule, event, notification_method,
                               event_revision=None,
                               event_updated_fields=None,
                               event_details_updated_fields=None):
    '''
    Render an alert context for the given parameters. Assume that the parameters are
    valid and that permissions have been respected.
    :param alert_rule: The alert rule that indicated the message.
    :param event:
    :param notification_method: The method for sending the alert.
    :return: A dict containing the alert context.
    '''
    eventdata = render_event(event, notification_method.owner)

    if not eventdata:
        return None

    eventdata['title'] = eventdata['title'] or event.title

    logger.debug('Rendered event: %s', json.dumps(
        eventdata, indent=2, default=str))

    # Render display titles and values
    schema = schema_utils.get_schema_renderer_method()(event.event_type.schema)
    pretty_details = {}
    event_details = eventdata.get('event_details', {}) or {}

    # Get details with display values
    details = schema_utils.get_details_and_display_values(event, schema)

    for k in event_details.keys():
        key_display = schema_utils.get_display_value_header_for_key(schema, k)
        if key_display not in details.keys():
            # different property & def titles, get alternative title
            key_display = schema_utils.find_display_value_for_key_in_definition(
                schema, k)

        pretty_details[k] = {'title': key_display,
                             'value': render_pretty_value(details[key_display])}

        old_internal_value = event_details_updated_fields.get(k)

        if old_internal_value:
            old_internal_value = old_internal_value.get('old')
            pretty_details[k]['old_value'] = render_pretty_value(
                old_internal_value)

    priority_color = priority_label_colors.get(
        event.priority_label, priority_label_color_default)

    if event.location:
        location = {
            'longitude': event.location.x,
            'latitude': event.location.y,
            'title': 'Location',
            'value': f'lon: {event.location.x:.3f}, lat: {event.location.y:.3f}',
            'href': f'https://{settings.SERVER_FQDN}?lnglat={event.location.x:.4f},{event.location.y:.4f}'
        }
    else:
        location = {
            'title': 'Location',
            'value': 'n/a',
        }

    # Notes
    current_time = datetime.now(tz=pytz.utc)
    notes_list = [
        {'updated_at': n.updated_at,
         'text': n.text,
         'username': n.created_by_user.username if n.created_by_user else 'n/a',
         'recently_updated': abs((event.updated_at - n.updated_at).total_seconds()) <= 2
         }
        for n in event.notes.all().order_by('-updated_at')
    ]

    # Resolve a nice display for "Reported By"
    reported_by = event.reported_by

    if hasattr(reported_by, 'get_full_name'):
        reported_by = reported_by.get_full_name()
    elif hasattr(reported_by, 'name'):
        reported_by = reported_by.name
    else:
        reported_by = 'n/a'

    # State
    state = {'title': 'State', 'value': coerce_state_value(event=event)}
    if 'state' in event_updated_fields and 'old' in event_updated_fields['state']:
        state['old_value'] = coerce_state_value(
            val=event_updated_fields['state'].get('old', ''))

    # Priority
    priority = {'title': 'Priority', 'value': event.priority_label,
                'style': f'background-color:{priority_color}'}
    if 'priority' in event_updated_fields and 'old' in event_updated_fields['priority']:
        priority['old_value'] = event_updated_fields['priority'].get('old')

    revision_action = event_revision.action if event_revision else 'updated'
    message_subject = ' '.join(
        (create_email_subject(event), f'({revision_action})'))

    report_context = {
        'alert': {
            'time': {'title': 'Alert Time', 'value': timezone.now()},
        },
        'site_name': settings.UI_SITE_NAME,
        'site_url': settings.UI_SITE_URL,
        'message_subject': message_subject,
        'alert_rule': alert_rule.display_title,
        'event': {
            'revision_action': revision_action,
            'state': state,
            'resolved': event.state == 'resolved',
            'serial_number': {'title': 'Report ID', 'value': event.serial_number},
            'time': {'title': 'Event Time', 'value': event.event_time},
            'priority': priority,
            'title': {'title': 'Title', 'value': event.display_title},
            'location': location,
            'reported_by': {"title": "Reported By", "value": reported_by}
        },
        'raw_event_details': eventdata.get('event_details', {}) or {},
        'pretty_details': pretty_details,
        'notes': notes_list,
    }

    return report_context


def create_email_subject(event):
    priority = event.priority_label
    title = event.title or event.event_type.display
    # resolved = 'Resolved ' if event.state == 'resolved' else ''
    return f"EarthRanger {priority} Report {event.serial_number}: {title}"
