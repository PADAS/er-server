import datetime
import json
import logging
from collections import namedtuple
from functools import partial
from uuid import UUID

from celery_once import QueueOnce

from django.db import close_old_connections
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from accounts.models.user import User
from activity.models import Event, Patrol
from activity.serializers import EventSerializer
from activity.serializers.patrol_serializers import PatrolSerializer
from activity.views import EventView, PatrolView
from das_server import celery, pubsub
from observations import servicesutils
from observations.models import Announcement, Message, SocketClient
from observations.serializers import AnnouncementSerializer, MessageSerializer
from observations.utils import get_position, LOCATION, get_user_key
from observations.views import ObservationsView, SubjectStatusView
from rt_api import client
from rt_api.rest_api_interface.dummy_request import DummyRequest
from utils.stats import update_gauge

logger = logging.getLogger(__name__)

EmitData = namedtuple('EmitData', ['type', 'sid', 'object_id', 'data'])


def get_context():
    return {'request': DummyRequest(uri='', http_method='GET')}


def dumps_helper(obj):
    if isinstance(obj, datetime.datetime):
        serial = obj.isoformat()
        return serial
    elif isinstance(obj, UUID):
        return str(obj)
    raise TypeError("Type not serializable: " + type(obj).__name__)


def get_username_sids_map():
    all_connections = client.get_all_connections_list()

    user_sids_map = {}
    for sid, session_data in all_connections.items():
        try:
            session_data = json.loads(session_data.decode('utf-8'))
            sid = sid.decode('UTF-8')
            username = session_data['username']
            user_sids_map.setdefault(username, set()).add(sid)
        except (UnicodeDecodeError, KeyError):
            logger.warning('Failed to parse session_data=%s', session_data)

    return user_sids_map


def get_sid_user(username, user_sids):
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        logger.warning('realtime-handler found no username=%s.', username)
        client.remove_clients(user_sids)


def get_emit_data(**kwargs):
    emit_data = EmitData(**kwargs)._asdict()
    return dict(emit_data)


def _event_handler(event_id, type_):
    try:
        logger.debug("Processing type=%s on event=%s", type_, event_id)
        event_view = EventView()

        user_sids_map = get_username_sids_map()
        logger.debug("user_sids_map: %s", user_sids_map)

        for username, user_sids in user_sids_map.items():
            user = get_sid_user(username, user_sids)
            if not user:
                continue

            logger.debug("Handling event for user: %s", username)
            # TODO: update this logic to be a little more frugal with the per
            # user/event-filter query.
            for sid in user_sids:
                emit_data = {}
                matches_current_filter = False

                if type_ == "delete_event":
                    emit_data = get_emit_data(
                        type=type_,
                        sid=sid,
                        object_id=event_id,
                        data={
                            "type": type_,
                            "event_id": event_id,
                            "event_data": None,
                            "matches_current_filter": matches_current_filter,
                        },
                    )
                else:
                    key = get_user_key(user, LOCATION)
                    location = get_position(key)
                    query_params = {}
                    if location:
                        location = (
                            f"{location.get('position').get('longitude')},{location.get('position').get('latitude')}"
                        )
                        query_params["location"] = location

                    request = DummyRequest(
                        user=user, http_method="GET", query_parameters=query_params
                    )
                    request = Request(request)  # Wrap in DRF Request
                    queryset = Event.objects.filter(id=event_id)
                    event = queryset.first()

                    if event:
                        event_count = 1
                        try:
                            event_view.check_object_permissions(
                                request=request, obj=event
                            )
                        except PermissionDenied:
                            logger.debug(
                                "Permission denied. user=%s, event=%s",
                                username,
                                event.id,
                            )
                        else:
                            matches_current_filter = True
                            should_annotate = False
                            try:
                                socket_client = SocketClient.objects.get(id=sid)
                                should_annotate = should_annotate_filtered_events(
                                    socket_client.event_filter
                                )
                                queryset = get_filtered_events(
                                    socket_client.event_filter, queryset
                                )
                                matches_current_filter = queryset.exists()

                            except SocketClient.DoesNotExist:
                                logger.debug(
                                    f"SocketClient does not exist for sid={sid}"
                                )

                            if should_annotate or matches_current_filter:
                                data = EventSerializer(
                                    event,
                                    context={
                                        "request": request,
                                        "include_related_events": True,
                                    },
                                ).data

                                emit_data = get_emit_data(
                                    type=type_,
                                    sid=sid,
                                    object_id=event_id,
                                    data={
                                        "type": type_,
                                        "event_id": event_id,
                                        "matches_current_filter": matches_current_filter,
                                        "event_data": data,
                                        "count": event_count,
                                    },
                                )

                if emit_data:
                    logger.debug("Publish das.realtime.emit.  data=%s", emit_data)
                    pubsub.publish(
                        json.dumps(emit_data, default=dumps_helper), "das.realtime.emit"
                    )

    finally:
        close_old_connections()


def should_annotate_filtered_events(event_filter):
    # TODO: Better way to detect the caller wants us to return all events, but
    # mark it as being filtered or not by current event filter
    return "filter" in event_filter


def get_filtered_events(event_filter, queryset):
    filter = event_filter.get("filter", event_filter)

    # Add state to event filter
    if event_filter.get("state"):
        filter["state"] = event_filter.get("state")

    return queryset.by_event_filter(filter)


def get_filtered_patrols(patrol_filter, queryset):
    if patrol_filter.get("filter"):
        filters = patrol_filter["filter"]
        queryset = queryset.by_patrol_filter(filters)

    if patrol_filter.get("status"):
        queryset = queryset.by_state(patrol_filter["status"])
    return queryset


@celery.app.task(base=QueueOnce, once={'graceful': True}, rate_limit='10/m')
def _broadcast_service_status(service_status_data=None):

    service_status_data = service_status_data or servicesutils.get_source_provider_statuses()

    try:
        all_connections = client.get_all_connections_list()

        logger.info({'rt.conn.count': len(all_connections)})
        for sid, session_data in all_connections.items():
            sid = sid.decode('utf8')

            emit_data = {
                'type': 'service_status',
                'sid': sid,
                'data': {
                    'services': service_status_data
                }
            }

            logger.info('Emitting %s to sid %s', emit_data, sid)
            payload = json.dumps(emit_data, default=dumps_helper)
            pubsub.publish(payload, routing_key='das.realtime.emit')
    except:
        logger.exception('Error emitting service status information.')
    finally:
        close_old_connections()


@celery.app.task()
def broadcast_service_status():
    _broadcast_service_status.apply_async()


def _subjectstatus_update_handler(subject_id):
    try:
        logger.debug(
            'Processing subjectstatus update for subject_id=%s', subject_id)

        # Curry this getter to re-use the view in the for-loop below.
        get_subjectstatus_payload = partial(
            get_subjectstatus_view, SubjectStatusView.as_view())

        get_observations_payload = partial(
            get_observations_view, ObservationsView.as_view())

        user_sids_map = get_username_sids_map()
        logger.debug('user_sids_map: %s', user_sids_map)

        for username, user_sids in user_sids_map.items():
            try:
                user = get_sid_user(username, user_sids)
                if not user:
                    continue

                # If subject-status payload is not None, then emit it.
                payload = get_subjectstatus_payload(user, subject_id)

                logger.debug('SubjectStatus payload: %s', payload)
                if payload:

                    emit_data = {
                        'type': 'subject_status',
                        'sid': '<<sid>>',
                        'object_id': subject_id,
                        'data': payload
                    }
                    emit_data = json.dumps(emit_data, default=dumps_helper)

                    for sid in user_sids:

                        message = emit_data.replace('<<sid>>', sid)

                        logger.debug('Emitting: %s', message)
                        pubsub.publish(
                            message, routing_key='das.realtime.emit')
                else:
                    logger.warning(
                        'SubjectStatus payload is empty.', extra=dict(username=username, subject_id=subject_id))

                # emit batch observations
                for sid in user_sids:
                    created_after = client.get_sid_subject_timestamp(
                        sid, subject_id)

                    payload = get_observations_payload(
                        user, subject_id, created_after=created_after)

                    if payload:
                        # TODO: move this order-by clause into the view.
                        points = sorted(
                            payload, key=lambda x: x['time'], reverse=True)

                        emit_data = get_emit_data(type='subject_track_merge', sid=sid, object_id=subject_id,
                                                  data={'points': points, 'subject_id': subject_id})

                        emit_message = json.dumps(
                            emit_data, default=dumps_helper)

                        logger.debug("Emitting: %s", emit_message)
                        pubsub.publish(
                            emit_message, routing_key='das.realtime.emit')

                    else:
                        logger.warning(
                            'Observation payload is empty.', extra=dict(username=username, subject_id=subject_id))

                    client.save_session_timestamp(sid, subject_id)

            except:
                logger.exception(
                    'Error creating subject-status payload. username=%s', username)
            finally:
                close_old_connections()
    finally:
        close_old_connections()


def _observation_handler(subject_id):
    # subject_position_update is no longer used. So delegate to subjectstatus
    # handler.
    _subjectstatus_update_handler(subject_id)


def get_subjectstatus_view(view, user, subject_id):
    # Create a dummy request with the user's info so we get the permission
    # enforcement for free
    request = DummyRequest(
        uri=f'/subject/{str(subject_id)}/status', http_method='GET', user=user)

    result = view(request, subject_id=subject_id,)

    # If there's nothing to send, no need to send it
    logger.debug('SubjectStatusView result: %s', result)
    if result.status_code != 200 or not result.data:
        return

    return result.data


def get_observations_view(view, user, subject_id, created_after):
    url = reverse('observations-list-view')
    query_parameter = {
        'subject_id': subject_id,
        'json_format': 'flat',
        'created_after': created_after
    }
    request = DummyRequest(uri=url, http_method='GET',
                           user=user, query_parameters=query_parameter)

    result = view(request, subject_id=subject_id)
    if result.status_code != 200 or not result.data.get('results'):
        return
    return result.data.get('results')


@celery.app.task()
def handle_new_event(event_id):
    logger.info('Celery worker handling new event_id: %s',
                event_id, extra={'rt.event': 'new'})
    _event_handler(event_id, 'new_event')


@celery.app.task()
def handle_update_event(event_id):
    logger.info('Celery worker handling update event_id: %s',
                event_id, extra={'rt.event': 'update'})
    _event_handler(event_id, 'update_event')


@celery.app.task()
def handle_delete_event(event_id):
    logger.info('Celery worker handling delete event_id: %s',
                event_id, extra={'rt.event': 'delete'})
    _event_handler(event_id, 'delete_event')


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def handle_new_subject_observation(subject_id):
    logger.info(
        'Celery worker handling new observation.', extra={'subject_id': subject_id,  'rt.event': 'new_subject_obs'})
    _observation_handler(subject_id)


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def handle_subjectstatus_update(subject_id):
    logger.info(
        'Celery worker handling subjectstatus update.', extra={'subject_id': subject_id,
                                                               'rt.event': 'subjectstatus_update'})
    _subjectstatus_update_handler(subject_id)


def _patrol_handler(item_id, type):
    try:
        logger.debug('Processing type=%s on patrol=%s', type, item_id)
        model, view, serializer = Patrol, PatrolView(), PatrolSerializer
        user_sids_map = get_username_sids_map()
        logger.debug('user_sids_map: %s', user_sids_map)

        try:
            queryset = model.objects.filter(id=item_id)
            instance = queryset.first()
        except model.DoesNotExist:
            instance = None
            if type != 'delete_patrol':
                logger.warning(
                    'Patrol handler given id: %s but it is not found in the database.')
                return

        for username, user_sids in user_sids_map.items():
            user = get_sid_user(username, user_sids)
            if not user:
                continue

            logger.debug('Handling patrol for user: %s', username)

            for sid in user_sids:
                emit_data = {}
                matches_current_filter = False
                if type == 'delete_patrol':
                    data = {'type': type, 'patrol_id': item_id,
                            'matches_current_filter': matches_current_filter}
                    emit_data = get_emit_data(
                        type=type, sid=sid, object_id=item_id, data=data)

                else:
                    request = DummyRequest(
                        user=user, http_method='GET', query_parameters={})
                    request = Request(request)  # Wrap in DRF Request

                    if instance:
                        try:
                            view.check_object_permissions(
                                request=request, obj=instance)
                        except PermissionDenied:
                            logger.debug(
                                'Permission denied. user=%s, patrol=%s', username, instance.id)
                        else:
                            matches_current_filter = True
                            try:
                                socket_client = SocketClient.objects.get(
                                    id=sid)
                            except SocketClient.DoesNotExist:
                                logger.debug(
                                    f'SocketClient does not exist for sid={sid}')
                            else:
                                queryset = get_filtered_patrols(
                                    socket_client.patrol_filter, queryset)
                                matches_current_filter = queryset.exists()

                            data = serializer(instance, context={
                                              'request': request}).data

                            emit_data = get_emit_data(type=type, sid=sid, object_id=item_id,
                                                      data={'type': type, 'patrol_id': item_id, 'patrol_data': data,
                                                            'matches_current_filter': matches_current_filter})

                if emit_data:
                    logger.debug(
                        'Publish das.realtime.emit.  data=%s', emit_data)
                    pubsub.publish(json.dumps(
                        emit_data, default=dumps_helper), 'das.realtime.emit')
    finally:
        close_old_connections()


def _radio_message_handler(object_id, action='radio_message'):
    try:
        logger.debug('Processing type=%s on message=%s', action, object_id)

        user_sids_map = get_username_sids_map()
        logger.debug('user_sids_map: %s', user_sids_map)

        for username, user_sids in user_sids_map.items():
            user = get_sid_user(username, user_sids)
            if not user:
                continue

            request = DummyRequest(
                user=user, http_method='GET', query_parameters={})
            request = Request(request)  # Wrap in DRF Request

            for sid in user_sids:
                if action == 'delete_message':
                    emit_data = get_emit_data(
                        type=action,
                        sid=sid,
                        object_id=object_id,
                        data={'type': action, 'data': {'id': object_id}})
                else:
                    try:
                        instance = Message.objects.get(id=object_id)
                    except Message.DoesNotExist:
                        instance = None
                    else:
                        message_data = MessageSerializer(instance, context={
                            'request': request}).data
                        emit_data = get_emit_data(
                            type=action,
                            sid=sid,
                            object_id=object_id,
                            data={'type': action, 'data': message_data})

                        logger.debug(
                            'Publish das.realtime.emit.  data=%s', emit_data)
                        pubsub.publish(json.dumps(
                            emit_data, default=dumps_helper), 'das.realtime.emit')
    finally:
        close_old_connections()


def _announcement_handler(object_id, action):
    try:
        logger.debug('Processing type=%s on message=%s', action, object_id)

        user_sids_map = get_username_sids_map()
        logger.debug('user_sids_map: %s', user_sids_map)

        for username, user_sids in user_sids_map.items():
            user = get_sid_user(username, user_sids)
            if not user:
                continue

            request = DummyRequest(
                user=user, http_method='GET', query_parameters={})
            request = Request(request)  # Wrap in DRF Request

            for sid in user_sids:
                try:
                    instance = Announcement.objects.get(id=object_id)
                except Announcement.DoesNotExist:
                    logger.warning(
                        'Announcement with this id: %s not found in the database.')
                else:
                    message_data = AnnouncementSerializer(instance, context={
                        'request': request}).data
                    emit_data = get_emit_data(
                        type=action,
                        sid=sid,
                        object_id=object_id,
                        data={'type': action, 'data': message_data})

                    logger.debug(
                        'Publish das.realtime.emit.  data=%s', emit_data)
                    pubsub.publish(json.dumps(
                        emit_data, default=dumps_helper), 'das.realtime.emit')
    finally:
        close_old_connections()


@celery.app.task()
def handle_new_patrol(patrol_id):
    logger.info('Celery worker handling new patrol_id: %s',
                patrol_id, extra={'rt.patrol': 'new'})
    _patrol_handler(patrol_id, 'new_patrol')


@celery.app.task()
def handle_update_patrol(patrol_id):
    logger.info('Celery worker handling update patrol_id: %s',
                patrol_id, extra={'rt.patrol': 'update'})
    _patrol_handler(patrol_id, 'update_patrol')


@celery.app.task()
def handle_delete_patrol(patrol_id):
    logger.info('Celery worker handling delete patrol_id: %s',
                patrol_id, extra={'rt.patrol': 'delete'})
    _patrol_handler(patrol_id, 'delete_patrol')


@celery.app.task()
def handle_new_message(message_id):
    logger.info(f'Celery worker handling new message id: {message_id}',
                extra={'rt.message': 'new_message'})
    _radio_message_handler(message_id)


@celery.app.task()
def handle_update_message(message_id):
    logger.info(f'Celery worker handling update message id: {message_id}',
                extra={'rt.message': 'update_message'})
    _radio_message_handler(message_id)


@celery.app.task()
def handle_delete_message(message_id):
    logger.info(f'Celery worker handling deleting message id: {message_id}',
                extra={'rt.message': 'delete_message'})
    _radio_message_handler(message_id, 'delete_message')


@celery.app.task()
def handle_new_announcement(announcement_id):
    logger.info(f'Celery worker handling new announcement id: {announcement_id}',
                extra={'rt.message': 'new_announcement'})
    _announcement_handler(announcement_id, 'new_announcement')


@celery.app.task()
def handle_emit_data(event_id):
    logger.info('event mailer event_id: %s', event_id)


@celery.app.task()
def check_redis_queues():
    """
    Periodic check of redis connections and queue sizes, ship them to statsd
    """
    logger.debug('Checking redis connectivity')
    conns = client.get_all_connections()
    conn_count = len(conns)
    logger.debug({'redis.conn.count': conn_count})

    realtime_session_count = client.get_session_count()

    # realtime queues
    # TODO - encapsulte the queries into a rt_api.queue_client
    rt_p1 = client.list_len('realtime_p1')
    rt_p2 = client.list_len('realtime_p2')
    rt_p3 = client.list_len('realtime_p3')
    logger.debug({'rt.realtime.p1': rt_p1})
    logger.debug({'rt.realtime.p2': rt_p2})
    logger.debug({'rt.realtime.p3': rt_p3})

    logger.debug({'rt.realtime.client_count': realtime_session_count})

    for key, value in [
        ('redis_connection_count', conn_count),
        ('rt_session_count', realtime_session_count),
    ]:
        update_gauge(metric=key, value=value, tags=['service:rt_api'])

    for key, value in [
        ('realtime_p1', rt_p1),
        ('realtime_p2', rt_p2),
        ('realtime_p3', rt_p3),
    ]:
        update_gauge(metric="task_queue_length",
                     value=value, tags=[f'queue:{key}'])

    for key, value in [
        ('default', client.list_len('default')),
        ('analyzers',  client.list_len('analyzers')),
        ('maintenance', client.list_len('maintenance')),
    ]:
        update_gauge(metric="task_queue_length",
                     value=value, tags=[f'queue:{key}'])

    memory_info = client.info('memory')

    val = -1
    try:
        val = memory_info['used_memory'] / memory_info['maxmemory']
    except ZeroDivisionError:
        val = memory_info['used_memory'] / memory_info['total_system_memory']

    update_gauge('redis_memory_gauge', val)

    logger.debug('redis_memory_use', extra={
        'used_memory': memory_info.get('used_memory', -1),
        'maxmemory': memory_info.get('maxmemory', -1),
        'total_system_memory': memory_info.get('total_system_memory', -1),
        'memory_gauge': val,
    })
