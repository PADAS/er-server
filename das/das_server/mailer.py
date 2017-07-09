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
email_separator_string = '{0}: {1}'

ignore_fields = ['sort_at', 'updated_at', 'created_at', 'updates', 'image_url',
                 'priority', 'geojson', 'location', 'event_details', 'id',
                 'serial_number', 'state', 'photos', 'is_contained_in', 'url',
                 'event_category', 'is_collection', 'attributes', 'provenance',
                 'priority_label', 'title', 'files']


def extract_details(schema, details):
    schema = schema_utils.get_rendered_schema(schema)
    for k in sorted(details.keys()):
        v = details[k]
        key_display = schema[k]['title']
        if isinstance(v, dict) and 'name' in v:
            yield email_separator_string.format(key_display, v['name'])
        elif isinstance(v, (int, float, bool)):
            yield email_separator_string.format(key_display, str(v))
        elif isinstance(v, str):
            yield email_separator_string.format(key_display, v)
        elif isinstance(v, list):
            yield email_separator_string.format(key_display, ', '.join([_.get('name') for
                                                                        _ in v if isinstance(_, dict) and _.get('name') is not None]))


def send_event_mail(event, user, revision, email_callback):
    if revision is not None:
        updated_fields = []
        for key, value in revision.data.items():
            if (key in ignore_fields and key != 'title') or value is None:
                continue
            try:
                display_value = event.get_display_value(key, value)
            except Exception:
                display_value = value
            updated_fields.append(
                email_separator_string.format(key, display_value))

        newness = _('UPDATE')
        if not updated_fields:
            # No visible updates, so don't send
            return
    else:
        newness = _('NEW')

    priority_str = event.get_display_value('priority', event.priority)
    subject_str = _('DAS {color} Alert: {id} {title}').format(
        color=priority_str,
        id=event.serial_number,
        title=event.title,
        newness=newness)

    schema_fields_and_values = None
    ed = event.event_details.first()
    if ed and ed.data and 'event_details' in ed.data:
        schema_fields_and_values = list(extract_details(
            event.event_type.schema, ed.data['event_details']))

    event_fields_and_values = []
    serializer = EventSerializer()
    serializer.context['request'] = DummyRequest()
    serializer.context['request'].user = user
    all_event_fields = serializer.to_representation(event)
    for i, (key, value) in enumerate(all_event_fields.items()):
        if key in ignore_fields or value is None:
            continue
        elif key == 'time' and event.time is not None:
            display_value = event.time.strftime('%A, %B %d, %Y at %H:%M')
        elif key == 'notes' and value is not None:
            try:
                display_value = ''
                notes_serializer = EventNoteSerializer()
                display_value = '\n'.join(
                    [notes_serializer.get_display_value(note) for note in
                     event.notes.all()])
            except Exception:
                display_value = value
        elif key == 'reported_by' and value is not None:
            display_value = value['username'] if 'username' in value else value
        else:
            try:
                display_value = event.get_display_value(key, value)
            except Exception:
                display_value = value
        if display_value is not None:
            event_fields_and_values.append(
                email_separator_string.format(key, display_value))

    parent_event = Event.objects.filter(
        out_relationship__to_event=event, out_relationship__type__value='contains').first()
    display_title = event.title if event.title is not None else _('No Title')
    parameters = {
        'id': event.serial_number,
        'title': display_title,
        'newness': newness,
        'color': priority_str,
        'parent': parent_event.serial_number if parent_event is not None else 0,
        'event_fields_and_values': event_fields_and_values,
        'schema_fields_exist': schema_fields_and_values is not None,
        'schema_fields_and_values': schema_fields_and_values
    }

    if revision is not None:
        parameters['user'] = revision.user
        parameters['updated_fields_names'] = updated_fields

    body = render_to_string(_('event_email.txt'), parameters)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))
    email_callback(subject_str, body, settings.FROM_EMAIL)


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
