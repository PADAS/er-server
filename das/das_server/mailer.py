import logging

from django.conf import settings
from django.template.loader import render_to_string
from activity.serializers import EventSerializer
from rt_api.rest_api_interface.dummy_request import DummyRequest

logger = logging.getLogger(__name__)

sms_separator_string = '{0}: {1}'
email_separator_string = '{0}: {1}'

raw_ignore_fields = ['sort_at', 'updated_at', ]
serialized_ignore_fields = ['sort_at', 'updated_at', 'updates', 'image_url', 'priority', ]


def send_new_event_mail(event, user):
    priority_str = event.get_display_value('priority', event.priority)
    subject_str = 'DAS {0} alert'.format(priority_str)

    parameters = {
        'event_id': event.id,
        'time': event.time,
        'priority': priority_str,
        'created_by': 'unknown'
    }
    if event.reported_by is not None:
        parameters['created_by'] = event.reported_by['name']

    body = render_to_string('new_event_email.txt', parameters)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))

    user.email_user(subject_str, body, settings.FROM_EMAIL)


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


def send_update_event_mail(event, changes, user):
    updated_fields = []
    for key in changes.data.keys():
        if key in raw_ignore_fields:
            continue
        updated_fields.append(key)

    all_fields_and_values = []
    serializer = EventSerializer()
    serializer.context['request'] = DummyRequest()
    all_event_fields = serializer.to_representation(event)
    for i, (key, value) in enumerate(all_event_fields.items()):
        if key in serialized_ignore_fields or value is None:
            continue
        try:
            display_value = event.get_display_value(key, value)
        except Exception as ex:
            display_value = value
        update_str = email_separator_string.format(key, display_value)
        if update_str is not None:
            all_fields_and_values.append(update_str)

    parameters = {
        'event': changes.object_id,
        'user': changes.user,
        'updated_fields_names': updated_fields,
        'all_fields_and_values': all_fields_and_values
    }

    priority_str = event.get_display_value('priority', event.priority)
    subject_str = 'DAS P{0} event {1} updated'.format(priority_str, event.id)

    body = render_to_string('update_event_email.txt', parameters)
    print(body)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))
    user.email_user(subject_str, body, settings.FROM_EMAIL)


def send_update_event_sms(event, changes, user):
    updates = []
    for key, value in changes.data.items():
        if key in raw_ignore_fields:
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


