import json
import logging
import urllib.parse
import uuid

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

import utils.schema_utils as schema_utils
from activity.alerting.businessrules import render_event
from activity.models import Event, NotificationMethod, AlertRule
from activity.serializers import EventSerializer, EventNoteSerializer
from das_server import mailer
from das_server import settings
from reports.distribution import send_report
from rt_api.rest_api_interface.dummy_request import DummyRequest

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

    # extract_event_data(event)

    return report_context


def create_email_subject(event):
    priority = event.priority_label
    title = event.title or event.event_type.display

    return f"EarthRanger {priority} Alert: [{event.serial_number}] {title}"


# Remainder is lifted from old 'mailer.py'

sms_separator_string = '{0}: {1}'
email_separator_string = ' {0} {1}: {2}'

ignore_fields = ['sort_at', 'updated_at', 'created_at', 'updates', 'image_url',
                 'priority', 'geojson', 'location', 'event_details', 'id',
                 'serial_number', 'state', 'photos', 'is_contained_in', 'url',
                 'event_category', 'is_collection', 'attributes', 'provenance',
                 'priority_label', 'files', 'message', 'related_subjects']

# For each deep-link code that the iOS app recognizes, provide a list of
# event types.
event_type_code_map = {
    'immobility': ['immobility', 'immobility_all_clear', ],
    'geofence': ['geofence_break', 'geofence', ],
    'low-speed': ['low_speed_wilcoxon', 'low_speed_wilcoxon_all_clear', 'low_speed_percentile' 'low_speed_percentile_all_clear', ],
    'proximity': ['proximity', ],
}

# Reverse the map, to event-type -> deep-link code.
event_type_code_map = dict((v, k)
                           for k, l in event_type_code_map.items() for v in l)

DISPLAY_TRANLATION = {
    'event_type': 'Report Type',
    'time': 'Created On',
}


def _get_display_value_for_key(key):
    return DISPLAY_TRANLATION.get(key) or key.replace('_', ' ').title()


def _get_key_title(key, schema):
    properties = schema['properties']
    if key in properties and 'title' in properties[key]:
        return properties[key]['title']

    definitions = schema.get('definitions', [])

    for definition_dictionary in [x for x in definitions if isinstance(x, dict)]:
        if definition_dictionary['key'] == key:
            return definition_dictionary['title']

    return None


def fetch_latest_location(subject):
    """
    Fetch Subject's latest location.
    :return: Latest latitude, latest longitude, latest observation time.
    """
    try:
        from observations.models import Observation
        observation = Observation.objects.filter(
            source__subjectsource__subject=subject).order_by(
            '-recorded_at')[0]
        return str(observation.location.y), str(observation.location.x), \
            observation.recorded_at.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.info(e)
        return '', '', ''


def build_deep_link_for_subject(event, subject, default_event_code='panic',
                                last_lat=None, last_lon=None):
    """
    Deep link must look like this:

    steta://?event={type}&name={name}&sys={source}&t={timestamp}&lat={lat}&lon={lon}&id={subject_id}

    """
    link_data = {
        'event': event_type_code_map.get(event.event_type.value, default_event_code),
        'name': subject.name,
        'id': str(subject.id),
        'sys': 'das',
        't': event.time.strftime('%Y-%m-%dT%H:%M:%S'),
        'lon': str(event.location.x),
        'lat': str(event.location.y),
    }
    if last_lat and last_lon:
        link_data.update({'last_lat': last_lat, 'last_lon': last_lon})

    qs = '&'.join('='.join((k, urllib.parse.quote(v)))
                  for k, v in link_data.items())
    return '?'.join(('steta://', qs))


def extract_details(schema, details, updated):
    if not details or not details.data or 'event_details' not in details.data:
        return

    details_dictionary = details.data['event_details']
    schema = schema_utils.get_rendered_schema(schema)
    properties = schema['properties']
    for k in sorted(details_dictionary.keys()):
        if k not in properties:
            continue
        update_indicator = '*' if k in updated else '-'
        v = details_dictionary[k]
        key_display = _get_key_title(k, schema)
        if not key_display:
            continue
        if isinstance(v, dict) and 'name' in v:
            yield email_separator_string.format(update_indicator, key_display, v['name'])
        elif isinstance(v, (int, float, bool)):
            yield email_separator_string.format(update_indicator, key_display, str(v))
        elif isinstance(v, str):
            try:
                uuid.UUID(v)
                v = schema['properties'][k]['enumNames'][v]
            except (ValueError, KeyError):
                pass
            yield email_separator_string.format(update_indicator, key_display, v)
        elif isinstance(v, list):
            yield email_separator_string.format(update_indicator, key_display, ', '.join([_.get('name') for
                                                                                          _ in v if isinstance(_, dict) and _.get('name') is not None]))


def get_revisions_for_event(event, revisions):
    '''
    Get the relevant revisions for the given Event.
    :param event:
    :param revisions:
    :return:
    '''
    event_rev_ids = []
    details_ids = []

    event_revisions = []
    details_revisions = []

    for revision in revisions:
        rev_info = revision.split(';')
        if rev_info[1] == '0':
            continue
        if rev_info[0] == 'e':
            event_rev_ids.append(rev_info[1])
        else:
            details_ids.append((rev_info[1], rev_info[2]))

    for event_rev_id in event_rev_ids:
        try:
            event_revisions.append(
                event.revision.all_user().get(id=event_rev_id))
        except ObjectDoesNotExist:
            # The revision id could be for a parent of sibiling event
            pass

    for details_id in details_ids:
        try:
            details_revisions.append(
                event.event_details.get(id=details_id[1]).revision.all_user().get(id=details_id[0]))
        except ObjectDoesNotExist:
            pass

    return event_revisions, details_revisions


def get_updated_field_names_for_revisions(event_revisions):
    '''
    TODO: Explain this function.
    :param event_revisions:
    :return:
    '''
    updated_fields = []
    for event_revision in event_revisions:
        updated_fields += list(event_revision.data.keys())

    return set(updated_fields)


def get_updated_schema_fields(event, details_revisions):
    '''
    Resolve the Event details fields that have been updated.
    :param event:
    :param details_revisions:
    :return:
    '''
    if len(details_revisions) == 0:
        return set()
    elif len(details_revisions) == 1:
        all_details_objects = list(
            event.event_details.all().order_by('updated_at'))
        if len(all_details_objects) == 1:
            return set(details_revisions[0].data['data']['event_details'].keys())
        else:
            details_revisions.append(all_details_objects[-2].revision.first())

    before = None
    diff = []
    for details_state in details_revisions:
        safe_details = []
        for item in details_state.data['data']['event_details'].items():
            safe_details.append((item[0], json.dumps(item[1])))
        if not before:
            before = set(safe_details)
            continue
        after = set(safe_details)
        diff += before ^ after
        before = after
    return set([item[0] for item in diff])


def extract_event_data(event, user, revisions):
    '''
    Build a rich detail view of the Event, for the given User.
    :param event:
    :param user:
    :param revisions:
    :return: (dict) a view of the Event including all that's necessary for rending an alert message.
    '''
    event_revisions, details_revisions = get_revisions_for_event(event, revisions)

    updated_fields = get_updated_field_names_for_revisions(event_revisions)
    updated_fields = updated_fields.union(
        get_updated_schema_fields(event, details_revisions))

    event_details = event.event_details.all().order_by('updated_at').last()
    schema_fields_and_values = list(extract_details(
        event.event_type.schema, event_details, updated_fields))

    child_events = Event.objects.filter(
        in_relationship__from_event=event, in_relationship__type__value='contains')
    child_event_data = []
    for child_event in child_events:
        child_event_data.append(
            extract_event_data(child_event, user, revisions))

    model_fields_and_values = []
    serializer = EventSerializer()
    serializer.context['request'] = DummyRequest()
    serializer.context['request'].user = user
    all_event_fields = serializer.to_representation(event)
    for i, (key, value) in enumerate(all_event_fields.items()):
        update_indicator = '*' if key in updated_fields else '-'
        if key == 'title':
            display_value = value or 'No Title'
        elif key in ignore_fields or value is None:
            continue
        elif key == 'time' and event.time is not None:
            display_value = event.time.strftime('%A, %B %d, %Y at %H:%M')
        elif key == 'notes' and value is not None:
            try:
                notes_serializer = EventNoteSerializer()
                display_value = '\n'.join(
                    [notes_serializer.get_display_value(note) for note in
                     event.notes.all()])
            except Exception:
                display_value = value
        elif key == 'reported_by' and value is not None:
            display_value = value.get('name') or value.get('username') or value
        else:
            try:
                display_value = event.get_display_value(key, value)
            except Exception:
                display_value = value
        if display_value is not None:
            model_fields_and_values.append(
                email_separator_string.format(update_indicator, _get_display_value_for_key(key), display_value))

    display_title = event.title if event.title is not None else _(
        'No Title')

    priority_str = event.get_display_value('priority', event.priority)

    event_data = {
        'id': event.serial_number,
        'title': display_title,
        'color': priority_str,
        'revised_fields': updated_fields,
        'priority': priority_str,
        'fields': schema_fields_and_values + model_fields_and_values,
        'children': child_event_data,
    }

    if event.event_type.value in getattr(settings, 'DEEP_LINK_EVENT_TYPES', []):
        deep_links = []
        for subject in event.related_subjects.all():
            last_lat, last_lon, last_fix_timestamp = fetch_latest_location(
                subject)
            event_data.get('fields', []).append(
                '  - Subject last known location ({}): lon={}, lat={}'.format(
                    last_fix_timestamp, last_lon, last_lat
                ))
            deep_links.append(
                '  - Subject Link: ' + build_deep_link_for_subject(
                    event, subject, last_lat=last_lat, last_lon=last_lon))
            deep_links.append(
                '  - Subject last known location link: '
                'https://maps.google.com/?q={},{}'.format(last_lat, last_lon))
        event_data['deep_links'] = deep_links
    return event_data


