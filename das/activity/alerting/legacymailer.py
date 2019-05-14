import json
import logging
import urllib.parse
import uuid

from django.utils.translation import ugettext_lazy as _
from django.db.models import ObjectDoesNotExist

import utils.schema_utils
from activity.models import Event
from activity.serializers import EventSerializer, EventNoteSerializer
from das_server import settings
from rt_api.rest_api_interface.dummy_request import DummyRequest

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

logger = logging.getLogger(__name__)


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


# Reverse the map, to event-type -> deep-link code.
event_type_code_map = dict((v, k)
                           for k, l in event_type_code_map.items() for v in l)

def extract_details(schema, details, updated):
    '''
    TODO: Description
    :param schema:
    :param details:
    :param updated:
    :return:
    '''
    if not details or not details.data or 'event_details' not in details.data:
        return

    details_dictionary = details.data['event_details']
    schema = utils.schema_utils.get_rendered_schema(schema)

    properties = schema['properties']
    for k in sorted(details_dictionary.keys()):
        if k not in properties:
            continue
        update_indicator = '*' if k in updated else '-'
        v = details_dictionary[k]
        key_display = _get_title_from_schema(k, schema)
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


def _get_updated_fields(event_revisions):
    '''
    TODO: Explain this function.
    :param event_revisions:
    :return:
    '''
    updated_fields = []
    for event_revision in event_revisions:
        updated_fields += list(event_revision.data.keys())

    return set(updated_fields)


def get_revised_fields(event):
    '''
    For the given event, determine the fields that have been updated in the
    latest revision. A new event should result in an empty set.
    :param event:
    :return: a set of field names.
    '''

    if event.revision.count() < 2:
        return set()

    current_revision = event.revision.latest('revised_at')

    try:
        previous_revision = current_revision.get_previous_by_revision_at(object_id=event.id)
    except ObjectDoesNotExist:
        return []
    else:
        return set(current_revision.data.keys())


def _get_updated_fields_within_details(event, details_revisions):
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

    # Diff logic.
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

    updated_fields = _get_updated_fields(event_revisions)
    updated_fields = updated_fields.union(
        _get_updated_fields_within_details(event, details_revisions))

    event_details = event.event_details.all().order_by('updated_at').last()
    schema_fields_and_values = list(extract_details(event.event_type.schema, event_details, updated_fields))

    child_events = Event.objects.filter(in_relationship__from_event=event, in_relationship__type__value='contains')

    child_event_data = []
    for child_event in child_events:
        child_event_data.append(extract_event_data(child_event, user, revisions))

    model_fields_and_values = []
    serializer = EventSerializer()
    serializer.context['request'] = DummyRequest()
    serializer.context['request'].user = user
    rendered_event = serializer.to_representation(event)

    for i, (key, value) in enumerate(rendered_event.items()):
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


#
# Helper functions below here.
#
DISPLAY_TRANLATION = {
    'event_type': _('Report Type'),
    'time': _('Created On'),
}

def _get_display_value_for_key(key):
    '''
    Translate an event attribute to a user-friendly name.
    :param key:
    :return: Either a friendly name or a title-cased version of the 'key'.
    '''
    return DISPLAY_TRANLATION.get(key) or key.replace('_', ' ').title()


def _get_title_from_schema(key, schema):

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


