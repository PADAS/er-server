import logging
import json
import uuid
import os

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist

from activity.serializers import EventSerializer, EventNoteSerializer
from activity.models import Event
from rt_api.rest_api_interface.dummy_request import DummyRequest
import utils.schema_utils as schema_utils


logger = logging.getLogger(__name__)

sms_separator_string = '{0}: {1}'
email_separator_string = ' {0} {1}: {2}'

ignore_fields = ['sort_at', 'updated_at', 'created_at', 'updates', 'image_url',
                 'priority', 'geojson', 'location', 'event_details', 'id',
                 'serial_number', 'state', 'photos', 'is_contained_in', 'url',
                 'event_category', 'is_collection', 'attributes', 'provenance',
                 'priority_label', 'files', 'message']


def get_display_value_for_key(key):
    if key == 'event_type':
        return 'Report Type'
    if key == 'time':
        return 'Created On'
    display = key.replace('_', ' ')
    return display.title()


def get_key_title(key, schema):
    properties = schema['properties']
    if key in properties and 'title' in properties[key]:
        return properties[key]['title']

    definitions = schema['defintions'] if 'definitions' in schema else []

    for definition_dictionary in [x for x in definitions if isinstance(x, dict)]:
        if definition_dictionary['key'] == key:
            return definition_dictionary['title']

    return None


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
        key_display = get_key_title(k, schema)
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
    updated_fields = []
    for event_revision in event_revisions:
        updated_fields += list(event_revision.data.keys())

    return set(updated_fields)


def get_updated_schema_fields(event, details_revisions):
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
    event_revisions, details_revisions = get_revisions_for_event(
        event, revisions)
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
                email_separator_string.format(update_indicator, get_display_value_for_key(key), display_value))

    display_title = event.title if event.title is not None else _(
        'No Title')

    priority_str = event.get_display_value('priority', event.priority)

    return {
        'id': event.serial_number,
        'title': display_title,
        'color': priority_str,
        'revised_fields': updated_fields,
        'priority': priority_str,
        'fields': schema_fields_and_values + model_fields_and_values,
        'children': child_event_data,
    }


def send_event_mail(event, user, revisions):
    data = extract_event_data(event, user, revisions)

    subject = _('DAS {color} Alert: {id} {title}').format(
        color=data['color'],
        id=data['id'],
        title=data['title'])

    body = render_to_string(_('incident_email.txt'), data).strip()
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))

    user.email_user(subject, body, settings.FROM_EMAIL)


def send_event_sms(event, user, revisions):
    data = extract_event_data(event, user, revisions)

    parameters = {'serial': data['id'],
                  'color': data['color'],
                  'title': data['title']}

    body = render_to_string('new_event_sms.txt', parameters).strip()
    logger.info('Sending new event sms to {0}'.format(user.phone))

    user.send_sms(body)
