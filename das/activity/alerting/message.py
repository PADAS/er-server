import json
import logging

from django.conf import settings
from django.db.models import ObjectDoesNotExist
from django.template.loader import render_to_string

import utils
from activity.alerting.businessrules import render_event
from activity.models import Event, NotificationMethod, AlertRule
from reports.distribution import send_report

import sendsms.api

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

    # Get Revisions
    event_revision, details_revision = resolve_event_revisions(event)

    # Calculate updated fields
    updated_event_fields = get_revised_event_fields(event_revision)
    updated_event_details_fields = get_revised_event_details_fields(details_revision)

    if 'priority' in updated_event_fields:
        updated_event_fields['priority']['new'] = event.get_priority_display()
        updated_event_fields['priority']['old'] = Event(priority=updated_event_fields['priority']['old'])\
            .get_priority_display()

    report_context = render_event_alert_context(alert_rule, event, notification_method,
                                                event_revisions=updated_event_fields,
                                                event_details_revisions=updated_event_details_fields)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f'Report context: {json.dumps(report_context, indent=2, default=str)}')
        logger.debug(f'Update Event Fields: {json.dumps(updated_event_fields, indent=2, default=str)}')
        logger.debug(f'Update Event Details Fields: {json.dumps(updated_event_details_fields, indent=2, default=str)}')

    email_body = render_to_string('eventalert.html', report_context)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f'Sending email body: {email_body}')

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
            'serial_number': event.serial_number,
            'color': 'gray',
            'title': event.title
        }
        sms_body = render_to_string('new_event_sms.txt', parameters).strip()

        sms_body = f'EarthRanger Alert ({event.priority}): {event.serial_number} {event.title}'
        sendsms.api.send_sms(body=sms_body, from_phone='2062147021', to=[notification_method.value,])
        logger.info(f"Sent sms alert {event_id} to {notification_method.value}")

    else:
        logger.error(f"Unsupported NotifcationMethod ({notification_method.method})"
                     f" when processing event:{event_id} for notification: {notification_method.id}")


def resolve_event_revisions(event):
    '''
    We end up in this code path in a few ways. Some data associated with the
    event has changed, but it could be the event itself or the event_details
    which contains the schema data. Or it could be both. It all depends on
    what fields were changed in the event update.

    To figure out what change(s) brought us here, we need to look at the
    timestamps on the latest revisions to both the event and eventdetails
    objects and see which one is newer.

    :param event_id:
    :return:
    '''
    revision = event.revision.all_user().latest('revision_at')
    try:
        details_revision = event.event_details.latest('updated_at') \
            .revision.all_user().latest('revision_at')
    except AttributeError:
        return revision, None

    diff = (revision.revision_at - details_revision.revision_at).total_seconds()

    # If the timestamps are < 1 second apart, they were very likely made
    # together
    if abs(diff) < 1:
        return revision, details_revision
    # If the changes are farther apart, take the later one only
    elif diff < 0:
        return None, details_revision
    else:
        return revision, None


def get_revised_event_fields(event_revision):

    if not event_revision:
        return {}

    try:
        previous_version = event_revision.get_previous_by_revision_at(object_id=event_revision.object_id)
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
        previous_version = event_details_revision.get_previous_by_revision_at(object_id=event_details_revision.object_id)
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

    changes = dict((k, {'new': v, 'old': previous.get(k)}) for k, v in current.items() if k not in ignore_these \
                   and v != previous.get(k))
    return changes


def _get_title_from_schema(key, schema):

    properties = schema['properties']
    if key in properties and 'title' in properties[key]:
        return properties[key]['title']

    definitions = schema.get('definitions', [])

    for definition_dictionary in [x for x in definitions if isinstance(x, dict)]:
        if definition_dictionary['key'] == key:
            return definition_dictionary['title']

    return None

priority_label_colors = {'Red': '#b00000',
                         'Amber': '#d97900',
                         'Green': '#00571c'
                         }

priority_label_color_default = '#3E4349'

def render_event_alert_context(alert_rule, event, notification_method,
                               event_revisions=None,
                               event_details_revisions=None):
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

    # Render display titles and values
    schema = utils.schema_utils.get_rendered_schema(event.event_type.schema)

    pretty_details = {}
    for k, internal_value in eventdata['event_details'].items():
        key_display = _get_title_from_schema(k, schema)
        rendered_value = internal_value.get('name') if isinstance(internal_value, dict) else internal_value
        pretty_details[k] = {'title': key_display,
                             'value': rendered_value}
        old_internal_value = event_details_revisions.get(k)
        if old_internal_value:
            old_internal_value = old_internal_value.get('old')
            rendered_old_value = old_internal_value.get('name') \
                if isinstance(old_internal_value, dict) else old_internal_value

            pretty_details[k]['old_value'] = rendered_old_value

    priority_color = priority_label_colors.get(event.priority_label, priority_label_color_default)

    if event.location:
        location = {
            'longitude': event.location.x,
            'latitude': event.location.y,
            'title': 'Location',
            'value': f'lon: {event.location.x}, lat: {event.location.y}',
            'href': f'http://www.google.com/maps/place/{event.location.y},{event.location.x}'
        }
    else:
        location = {
            'title': 'Location',
            'value': 'n/a',
        }

    # Notes
    notes_list = [
        {'updated_at': n.updated_at,
         'text': n.text,
         'username': n.created_by_user.username if n.created_by_user else 'n/a'
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

    report_context = {
        'site_name': settings.UI_SITE_NAME,
        'site_url': settings.UI_SITE_URL,
        'message_subject': create_email_subject(event),
        'alert_rule': alert_rule.title,
        'event': {
            'serial_number': {'title': 'Report ID', 'value': event.serial_number},
            'time': {'title': 'Event Time', 'value': event.event_time},
            'priority': {'title': 'Priority', 'value': event.priority_label,
                         'style': f'background-color:{priority_color}'},
            'title': {'title': 'Title', 'value': eventdata['title']},
            'location': location,
            'reported_by': {"title": "Reported By", "value": reported_by }
        },
        'raw_event_details': eventdata['event_details'],
        'pretty_details': pretty_details,
        'notes': notes_list,
    }

    return report_context


def create_email_subject(event):
    priority = event.priority_label
    title = event.title or event.event_type.display

    return f"EarthRanger {priority} Report {event.serial_number}: {title}"


