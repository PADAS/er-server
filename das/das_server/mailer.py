import logging
import json
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from activity.serializers import EventSerializer, EventNoteSerializer
from activity.models import Event, EventRelationship, EventRelationshipType
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


def extract_event_data(event, user, revision):
    revised_fields = revision.data.keys(
    ) if revision is not None and revision.object_id == event.id else []
    priority_str = event.get_display_value('priority', event.priority)
    ed = event.event_details.first()
    schema_fields_and_values = list(extract_details(
        event.event_type.schema, ed.data['event_details'], revised_fields)) if ed and ed.data and 'event_details' in ed.data else []
    child_events = Event.objects.filter(
        in_relationship__from_event=event, in_relationship__type__value='contains')
    child_event_data = []
    for child_event in child_events:
        child_event_data.append(
            extract_event_data(child_event, user, revision))

    model_fields_and_values = []
    serializer = EventSerializer()
    serializer.context['request'] = DummyRequest()
    serializer.context['request'].user = user
    all_event_fields = serializer.to_representation(event)
    for i, (key, value) in enumerate(all_event_fields.items()):
        update_indicator = '*' if key in revised_fields else '-'
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

    return {
        'id': event.serial_number,
        'title': display_title,
        'color': priority_str,
        'revised_fields': revised_fields,
        'priority': priority_str,
        'fields': schema_fields_and_values + model_fields_and_values,
        'children': child_event_data,

    }


def send_event_mail(event, user, revision, email_callback):
    alert_target = Event.objects.filter(
        out_relationship__to_event=event,
        out_relationship__type__value='contains').first() or event

    data = extract_event_data(alert_target, user, revision)

    subject = _('DAS {color} Alert: {id} {title}').format(
        color=data['color'],
        id=data['id'],
        title=data['title'])

    body = render_to_string(_('incident_email.txt'), data)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))
    email_callback(subject, body, settings.FROM_EMAIL)


def send_new_event_sms(event, user):
    priority_str = event.get_display_value('priority', event.priority)

    parameters = {
        'event_id': event.id,
        'time': event.time,
        'priority': priority_str,
        'created_by': 'unknown'
    }
    if event.reported_by is not None:
        parameters['created_by'] = event.reported_by['name']

    body = render_to_string('new_event_sms.txt', parameters)
    logger.info('Sending new event sms to {0}'.format(user.phone))

    user.send_sms(body, None)


def send_update_event_sms(event, changes, user):
    updates = []
    for key, value in changes.data.items():
        if key in ignore_fields:
            continue
        display_value = event.get_display_value(key, value)
        update_str = sms_separator_string.format(key, display_value)
        updates.append(update_str)

    parameters = {
        'event': changes.object_id,
        'user': changes.user,
        'updates': updates
    }

    body = render_to_string('update_event_sms.txt', parameters)[:100]
    logger.info('Sending new event sms to {0}'.format(user.phone))
    user.send_sms(body, None)
