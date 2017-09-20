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
from rt_api import client
import urllib.parse

from activity.permissions import EventCategoryPermissions
from activity.serializers import EventSerializer

from observations.models import SocketClient


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


def _event_handler(event_id, type):
    try:
        logger.debug('Processing type=%s on event=%s', type, event_id)
        event_view = EventView.as_view()
        all_connections = redis_client.hgetall(client.CLIENT_LIST_KEY)

        logger.debug('handling event for all_connections=%s', all_connections)
        for sid, session_data in all_connections.items():
            try:

                session_data = json.loads(session_data.decode('utf-8'))
                sid = sid.decode('UTF-8')
                username = session_data['username']

                logger.debug(
                    'Creating event payload for user=%s, sid=%s', username, sid)

                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    logger.warning(
                        'Lookup by username=%s found no user.', username)
                    client.remove_client(sid)
                    continue

                request = DummyRequest(user=user, http_method='GET')
                queryset = Event.objects.filter(id=event_id)

                try:
                    socket_client = SocketClient.objects.get(id=sid)
                    queryset = queryset.by_search_filter(
                        socket_client.event_filter)
                except SocketClient.DoesNotExist:
                    logger.debug('SocketClient does not exist for sid=%s', sid)

                event = queryset.first()

                # With search filter, it's possible to have no matching Event.
                if not event:
                    return

                try:
                    event_view.check_object_permissions(
                        request=request, obj=event)
                    data = EventSerializer(event).data

                    emit_data = {
                        'type': type,
                        'sid': sid,
                        'object_id': event_id,
                        'data': {'type': type, 'event_id': event_id, 'event_data': data}
                    }
                    # count_data = {
                    #     'type': 'count_event',
                    #     'sid': sid,
                    #     'data': Event.objects.new_count()
                    # }

                    logger.debug(
                        'Publish das.realtime.emit.  data=%s', emit_data)
                    pubsub.publish(json.dumps(
                        emit_data, default=dumps_helper), 'das.realtime.emit')
                    # pubsub.publish(json.dumps(
                    # count_data, default=dumps_helper), 'das.realtime.emit')
                except:
                    logger.exception('Permission denied.')

            except Exception as ex:
                logger.exception(
                    'Error creating custom payload for event: %s', event_id)
            finally:
                close_old_connections()

    finally:
        close_old_connections()


def _observation_handler(subject_id):
    try:
        logger.debug(
            'Processing new observation for subject_id=%s', subject_id)

        # Curry this getter to re-use the view in the for-loop below.
        get_subject_payload = partial(
            get_subject_view_details, SubjectTracksView.as_view())
        all_connections = redis_client.hgetall(client.CLIENT_LIST_KEY)

        for sid, session_data in all_connections.items():
            try:
                session_data = json.loads(session_data.decode('utf-8'))
                sid = sid.decode('UTF-8')
                username = session_data['username']

                logger.debug(
                    'Create observation payload. username=%s, sid=%s', username, sid)

                try:
                    logger.debug('Lookup username=%s', username)
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    logger.warning(
                        'Lookup by username. username=%s does not exist.', username)
                    client.remove_client(sid)
                    continue

                # If subject-view payload is not None, then emit it.
                payload = get_subject_payload(user, subject_id)
                if payload:
                    emit_data = {
                        'type': 'subject_position_update',
                        'sid': sid,
                        'object_id': subject_id,
                        'data': payload
                    }

                    pubsub.publish(json.dumps(
                        emit_data, default=dumps_helper), 'das.realtime.emit')

            except:
                logger.exception(
                    'Error creating observation payload. session_data=%s', session_data)
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
    logger.info('Celery worker handling new event_id: %s', event_id)
    _event_handler(event_id, 'new_event')


@celery.app.task()
def handle_update_event(event_id):
    logger.info('Celery worker handling update event_id: %s', event_id)
    _event_handler(event_id, 'update_event')


@celery.app.task()
def handle_delete_event(event_id):
    logger.info('Celery worker handling delete event_id: %s', event_id)
    _event_handler(event_id, 'delete_event')


@celery.app.task()
def handle_new_source_observation(source_id):
    logger.info(
        'Celery worker handling new observation. source_id=%s', source_id)
    subject_source = SubjectSource.objects.filter(source=source_id)\
        .order_by('assigned_range').reverse().first()
    _observation_handler(subject_source.subject_id)


@celery.app.task()
def handle_new_subject_observation(subject_id):
    logger.info(
        'Celery worker handling new observation. subject_id=%s', subject_id)
    _observation_handler(subject_id)


@celery.app.task()
def handle_emit_data(event_id):
    logger.info('event mailer event_id: %s', event_id)
