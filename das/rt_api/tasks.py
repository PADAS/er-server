import datetime
import json
import logging
import redis
from functools import partial

from celery_once import QueueOnce

from accounts.models.user import User
from activity.models import Event
from activity.views import EventView
from das_server import celery, pubsub
from django.conf import settings
from django.db import close_old_connections

from observations import servicesutils

from observations.models import SubjectSource
from observations.views import SubjectTracksView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from uuid import UUID
from rt_api import client

from activity.serializers import EventSerializer

from observations.models import SocketClient


logger = logging.getLogger(__name__)

queue_client = redis.from_url(settings.CELERY_BROKER_URL)


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
        event_view = EventView()

        all_connections = client.get_all_connections()

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

                request = DummyRequest(
                    user=user, http_method='GET', query_parameters={})
                queryset = Event.objects.filter(id=event_id)

                try:
                    socket_client = SocketClient.objects.get(id=sid)
                    queryset = queryset.by_event_filter(
                        socket_client.event_filter)
                except SocketClient.DoesNotExist:
                    logger.debug('SocketClient does not exist for sid=%s', sid)

                event = queryset.first()

                if event:
                    try:
                        event_view.check_object_permissions(
                            request=request, obj=event)
                    except:
                        logger.debug(
                            'Permission denied. user=%s, event=%s', username, event.id)
                    else:
                        data = EventSerializer(event,
                                               context={'request': request,
                                                        'include_related_events': True
                                                        }).data

                        emit_data = {
                            'type': type,
                            'sid': sid,
                            'object_id': event_id,
                            'data': {'type': type, 'event_id': event_id, 'event_data': data}
                        }

                        logger.debug(
                            'Publish das.realtime.emit.  data=%s', emit_data)
                        pubsub.publish(json.dumps(
                            emit_data, default=dumps_helper), 'das.realtime.emit')

            except Exception:
                logger.exception(
                    'Error creating custom payload for event: %s', event_id)

    finally:
        close_old_connections()


def _broadcast_service_status(service_status_data=None):

    service_status_data = service_status_data or servicesutils.get_source_provider_statuses()

    try:
        all_connections = client.get_all_connections()

        logger.info({'rt.conn.count': len(all_connections)})
        for sid, session_data in all_connections.items():
            sid = sid.decode('utf8')

            emit_data = {
                'type': 'service_status',
                'sid': sid,
                'data': service_status_data,
            }

            logger.info('Emitting %s to sid %s', emit_data, sid)
            payload = json.dumps(emit_data, default=dumps_helper)
            pubsub.publish(payload, routing_key='das.realtime.emit')
    except:
        logger.exception('Error emitting service status information.')
    finally:
        close_old_connections()


@celery.app.task(base=QueueOnce, once={'graceful': True, 'timeout': 60}, rate_limit='4/m')
def broadcast_service_status():
    _broadcast_service_status()


def _observation_handler(subject_id):
    try:
        logger.debug(
            'Processing new observation for subject_id=%s', subject_id)

        # Curry this getter to re-use the view in the for-loop below.
        get_subject_payload = partial(
            get_subject_view_details, SubjectTracksView.as_view())

        all_connections = client.get_all_connections()

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
                    logger.info(emit_data)
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
                           query_parameters={'limit': 2}, user=user)

    result = view(request, subject_id=subject_id,)

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
    properties = geojson_data['properties']

    # also need to send subject status if it exists
    if 'subject_state' in properties:
        payload['state'] = properties['subject_state']

    # Include radio details:
    for k in ('last_voice_call_start_at', 'requested_location_at'):
        if k in properties:
            payload[k] = properties[k]

    return payload


@celery.app.task()
def handle_new_event(event_id):
    logger.info('Celery worker handling new event_id: %s', event_id, extra={'rt.event': 'new'})
    _event_handler(event_id, 'new_event')


@celery.app.task()
def handle_update_event(event_id):
    logger.info('Celery worker handling update event_id: %s', event_id, extra={'rt.event': 'update'})
    _event_handler(event_id, 'update_event')


@celery.app.task()
def handle_delete_event(event_id):
    logger.info('Celery worker handling delete event_id: %s', event_id, extra={'rt.event': 'delete'})
    _event_handler(event_id, 'delete_event')


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def handle_new_source_observation(source_id):
    logger.info(
        'Celery worker handling new observation. source_id=%s', source_id, extra={'rt.event': 'new_source_obs'})
    subject_source = SubjectSource.objects.filter(source=source_id)\
        .order_by('assigned_range').reverse().first()
    _observation_handler(subject_source.subject_id)


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def handle_new_subject_observation(subject_id):
    logger.info(
        'Celery worker handling new observation. subject_id=%s', subject_id, extra={'rt.event': 'new_subject_obs'})
    _observation_handler(subject_id)


@celery.app.task()
def handle_emit_data(event_id):
    logger.info('event mailer event_id: %s', event_id)


@celery.app.task()
def check_redis_queues():
    """
    Periodic check of redis connections and queue sizes, so that we can expose them 
    to elasticsearch via a log message
    """
    logger.info('Checking redis connectivity')
    conn = queue_client.client_list()
    conn_count = len(conn)
    logger.info({'redis.conn.count': conn_count})
    # realtime queues
    # TODO - encapsulte the queries into a rt_api.queue_client
    rt_p1 = queue_client.llen('realtime_p1')
    rt_p2 = queue_client.llen('realtime_p2')
    rt_p3 = queue_client.llen('realtime_p3')
    logger.info({'rt.realtime.p1': rt_p1})
    logger.info({'rt.realtime.p2': rt_p2})
    logger.info({'rt.realtime.p3': rt_p3})


