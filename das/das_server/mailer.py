import logging
import json
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from activity.serializers import EventSerializer, EventNoteSerializer
from activity.models import Event
from rt_api.rest_api_interface.dummy_request import DummyRequest
import activity.schema_utils as schema_utils
import os

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


def extract_details(schema, details, updated):
    if not details or not details.data or 'event_details' not in details.data:
        return

    schema = schema_utils.get_rendered_schema(schema)
    for k in sorted(details.keys()):
        if k not in schema:
            continue
        update_indicator = '*' if k in updated else '-'
        v = details[k]
        key_display = schema[k]['title']
        if isinstance(v, dict) and 'name' in v:
            yield email_separator_string.format(update_indicator, key_display, v['name'])
        elif isinstance(v, (int, float, bool)):
            yield email_separator_string.format(update_indicator, key_display, str(v))
        elif isinstance(v, str):
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
        rev_type, rev_id = revision.split(';')
        if rev_id == '0':
            continue
        if rev_type == 'e':
            event_rev_ids.append(rev_id)
        else:
            details_ids.append(rev_id)

    for event_rev_id in event_rev_ids:
        try:
            event_revisions.append(
                event.revision.all_user().get(id=event_rev_id))
        except Exception as ex:
            print(ex)

    for details_id in details_ids:
        try:
            details_revisions.append(
                event.event_details.first().revision.all_user().get(id=details_id))
        except Exception as ex:
            print(ex)

    return event_revisions, details_revisions


def get_updated_field_names_for_revisions(event_revisions):
    updated_fields = []
    for event_revision in event_revisions:
        updated_fields += list(event_revision.data.keys())

    return set(updated_fields)


def get_updated_schema_fields(details_revisions):
    if len(details_revisions) < 2:
        return []

    before = None
    after = None
    diff = []
    for details_state in details_revisions:
        if not before:
            before = set(details_state.data['data']['event_details'].items())
            continue
        after = set(details_state.data['data']['event_details'].items())
        diff += before ^ after
        before = after
    return set([item[0] for item in diff])


def extract_event_data(event, user, revisions):
    event_revisions, details_revisions = get_revisions_for_event(
        event, revisions)
    updated_fields = get_updated_field_names_for_revisions(event_revisions)
    updated_fields += get_updated_schema_fields(details_revisions)

    event_details = event.event_details.first()
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
        if key in ignore_fields or value is None:
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

    body = render_to_string(_('incident_email.txt'), data)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))

    # user.email_user(subject, body, settings.FROM_EMAIL)


def send_event_sms(event, user, revisions):
    data = extract_event_data(event, user, revisions)

    parameters = {
        'event_id': event.id,
        'time': event.time,
        'priority': data['color'],
        'created_by': 'unknown'
    }
    if event.reported_by is not None:
        parameters['created_by'] = event.reported_by['name']

    body = render_to_string('new_event_sms.txt', parameters)
    logger.info('Sending new event sms to {0}'.format(user.phone))

    user.send_sms(body, None)
