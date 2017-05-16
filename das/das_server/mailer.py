import logging

from django.conf import settings
from html import unescape
from django.template.loader import render_to_string
from activity.serializers import EventSerializer
from rt_api.rest_api_interface.dummy_request import DummyRequest

logger = logging.getLogger(__name__)

sms_separator_string = '{0}: {1}'
email_separator_string = '{0}: {1}'

ignore_fields = ['sort_at', 'updated_at', 'created_at', 'updates', 'image_url',
                 'priority', 'geojson', 'location', 'event_details', 'id',
                 'serial_number']


def extract_details(details):
    for k, v in details.items():
        if isinstance(v, dict) and 'name' in v:
            yield email_separator_string.format(k, v['name'])
        elif isinstance(v, (int, float, bool)):
            yield email_separator_string.format(k, str(v))
        elif isinstance(v, str):
            yield email_separator_string.format(k, v)
        elif isinstance(v, list):
            yield email_separator_string.format(k, ', '.join([_.get('name') for
                _ in v if isinstance(_, dict) and _.get('name') is not None]))


def send_event_mail(event, user, revision, email_callback = None):
    if revision is not None:
        updated_fields = []
        for key, value in revision.data.items():
            if key in ignore_fields or value is None:
                continue
            try:
                display_value = event.get_display_value(key, value)
            except Exception:
                display_value = value
            updated_fields.append(email_separator_string.format(key, display_value))

        newness = 'UPDATE'
    else:
        newness = 'NEW'

    priority_str = event.get_display_value('priority', event.priority)
    subject_str = 'DAS {color} ALERT: {id}  {title} {newness}'.format(
        color=priority_str,
        id=event.serial_number,
        title=event.title,
        newness=newness)

    schema_fields_and_values = None
    ed = event.event_details.first()
    if ed and ed.data and 'event_details' in ed.data:
        schema_fields_and_values = list(
            extract_details(ed.data['event_details']))

    event_fields_and_values = []
    serializer = EventSerializer()
    serializer.context['request'] = DummyRequest()
    serializer.context['request'].user = user
    all_event_fields = serializer.to_representation(event)
    for i, (key, value) in enumerate(all_event_fields.items()):
        if key in ignore_fields or value is None:
            continue
        try:
            display_value = event.get_display_value(key, value)
        except Exception:
            display_value = value
        update_str = email_separator_string.format(key, display_value)
        if update_str is not None:
            event_fields_and_values.append(update_str)

    parameters = {
        'id': event.serial_number,
        'title': event.title,
        'newness': newness,
        'event_fields_and_values': event_fields_and_values,
        'schema_fields_exist': schema_fields_and_values is not None,
        'schema_fields_and_values': schema_fields_and_values
    }

    if revision is not None:
        parameters['user'] = revision.user
        parameters['updated_fields_names'] = updated_fields

    body = render_to_string('event_email.txt', parameters)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))
    if email_callback is None:
        user.email_user(subject_str, body, settings.FROM_EMAIL)
    else:
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


