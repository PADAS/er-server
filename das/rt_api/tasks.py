import datetime
import json
import logging
import redis
from functools import partial

from accounts.models.user import User
from activity.models import Event
from activity.views import EventView
from das_server import celery, pubsub
from django.conf import settings
from django.db import close_old_connections
from observations.models import SubjectSource
from observations.views import SubjectTracksView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from uuid import UUID


redis_client = redis.from_url(settings.REALTIME_BROKER_URL)

logger = logging.getLogger(__name__)


def get_context():
    return {'request': DummyRequest(uri='', http_method='GET')}


def dumps_helper(obj):
    if isinstance(obj, datetime.datetime):
        serial = obj.isoformat()
        return serial
    elif isinstance(obj, UUID):
        return str(obj)
    raise TypeError("Type not serializable: " + type(obj).__name__)


from observations.models import SocketClient


def _event_handler(event_id, type):
    try:
        logger.debug('Processing update on event_id {0}'.format(event_id))
        view = EventView.as_view()
        all_connections = redis_client.hgetall('realtime_connections')

        for sid, username in all_connections.items():
            try:
                connected_sid = sid.decode('UTF-8')
                username = username.decode('UTF-8')

                logger.debug('Creating event payload for user {0}: {1}'.format(
                    username[0], connected_sid))

                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    # Probably shouldn't get here, but maybe the user got
                    # deleted just now?
                    redis_client.hdel('realtime_connections', connected_sid)
                    continue

                socket_client = SocketClient.objects.get(id=sid)
                qp = {
                    'filter': json.dumps(socket_client.event_filter)
                }
                # Fake an API call for free permission enforcement
                request = DummyRequest(
                    '/event/', 'GET', user=user, query_parameters=qp)
                result = view(request, id=event_id)

                # If there's nothing to send, no need to send it
                if result.status_code != 200 or not result.data:
                    continue

                emit_data = {
                    'type': type,
                    'sid': connected_sid,
                    'object_id': event_id,
                    'data': {'type': type, 'event_id': event_id, 'event_data': result.data}
                }
                count_data = {
                    'type': 'count_event',
                    'sid': connected_sid,
                    'data': Event.objects.new_count()
                }

                pubsub.publish(json.dumps(
                    emit_data, default=dumps_helper), 'das.realtime.emit')
                pubsub.publish(json.dumps(
                    count_data, default=dumps_helper), 'das.realtime.emit')

            except Exception as ex:
                logger.exception(
                    'Error creating custom payload for event: ' + event_id)
            finally:
                close_old_connections()

    finally:
        close_old_connections()


def _observation_handler(subject_id):
    try:
        logger.debug(
            'Processing new observation for subject_id {0}'.format(subject_id))

        # Curry this getter to re-use the view in the for-loop below.
        get_subject_payload = partial(
            get_subject_view_details, SubjectTracksView.as_view())
        all_connections = redis_client.hgetall('realtime_connections')

        for sid, username in all_connections.items():
            try:
                connected_sid = sid.decode('UTF-8')
                username = username.decode('UTF-8')

                logger.debug('Creating observation payload for user {0}: {1}'.format(
                    username[0], connected_sid))

                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    # Probably shouldn't get here, but maybe the user got
                    # deleted just now?
                    redis_client.hdel('realtime_connections', connected_sid)
                    continue

                # If subject-view payload is not None, then emit it.
                payload = get_subject_payload(user, subject_id)
                if payload:
                    emit_data = {
                        'type': 'subject_position_update',
                        'sid': connected_sid,
                        'object_id': subject_id,
                        'data': payload
                    }

                    pubsub.publish(json.dumps(
                        emit_data, default=dumps_helper), 'das.realtime.emit')

            except Exception as ex:
                logger.exception(
                    'Error creating payload data for observation: ' + subject_id)
            finally:
                close_old_connections()
    finally:
        close_old_connections()


def get_subject_view_details(view, user, subject_id):
    # Create a dummy request with the user's info so we get the permission
    # enforcement for free
    request = DummyRequest('/subject/{0}/'.format(subject_id), 'GET',
                           {'limit': 2}, user=user)
    result = view(request, id=subject_id)

    # If there's nothing to send, no need to send it
    if result.status_code != 200 or not result.data or 'features' not in result.data or len(
            result.data['features']) == 0:
        return

    geojson_data = result.data['features'][0]

    # If there are no coordinates the user is allowed to see, no reason to
    # send a notification
    if len(geojson_data['geometry']['coordinates']) == 0:
        return

    payload = {'geo_json': geojson_data}

    # also need to send subject status if it exists
    if 'subject_state' in result.data.serializer.context:
        payload['state'] = result.data.serializer.context['subject_state']

    # Include radio details:
    for k in ('last_voice_call_start_at', 'requested_location_at'):
        if k in result.data.serializer.context:
            payload[k] = result.data.serializer.context[k]

    return payload


@celery.app.task()
def handle_new_event(event_id):
    logger.info('Celery worker handling new event_id: {}'.format(event_id))
    _event_handler(event_id, 'new_event')


@celery.app.task()
def handle_update_event(event_id):
    logger.info('Celery worker handling update event_id: {}'.format(event_id))
    _event_handler(event_id, 'update_event')


@celery.app.task()
def handle_delete_event(event_id):
    logger.info('Celery worker handling delete event_id: {}'.format(event_id))
    _event_handler(event_id, 'delete_event')


@celery.app.task()
def handle_new_source_observation(source_id):
    logger.info(
        'Celery worker handling new source observation: {}'.format(source_id))
    subject_source = SubjectSource.objects.filter(source=source_id)\
        .order_by('assigned_range').reverse().first()
    _observation_handler(subject_source.subject_id)


@celery.app.task()
def handle_new_subject_observation(subject_id):
    logger.info(
        'Celery worker handling new subject observation: {}'.format(subject_id))
    _observation_handler(subject_id)


@celery.app.task()
def handle_emit_data(event_id):
    logger.info('event mailer event_id: {}'.format(event_id))
