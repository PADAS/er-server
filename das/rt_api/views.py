import logging

import time
from datetime import datetime, timedelta
import pytz

import eventlet
from django.shortcuts import render
from django.views.generic import View
from django.conf import settings
from socketio.kombu_manager import KombuManager
from socketio.server import Server
from django.contrib.auth import authenticate
from django.db import close_old_connections

from rt_api.rest_api_interface.dummy_request import DummyRequest
from rt_api import client
import rt_api.pubsub_listener
import utils.json

logger = logging.getLogger('rt_api')

GLOBAL_SIO = None


class DasSocketServer(Server):
    '''
    Extend Server, to implement _trigger_event.

    TODO: It will be better to create class-based namespaces, which formally allow hooking
    into trigger_event.
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _trigger_event(self, event, namespace, *args):

        try:
            super()._trigger_event(event, namespace, *args)
        finally:
            close_old_connections()


def create_rt_socketio():
    global GLOBAL_SIO
    if GLOBAL_SIO is None:

        client_mgr = KombuManager(url=settings.REALTIME_BROKER_URL,
                                  transport_options=settings.REALTIME_BROKER_OPTIONS
                                  )
        server_options = dict(async_mode=settings.ASYNC_MODE)
        server_options['cors_credentials'] = \
            getattr(settings, 'CORS_ALLOW_CREDENTIALS', False)

        if not getattr(settings, 'CORS_ORIGIN_ALLOW_ALL', False):
            server_options['cors_allowed_origins'] = \
                getattr(settings, 'CORS_ORIGIN_WHITELIST', None)

        socketio_logger = logging.getLogger('rt_api.socketio')
        sio = DasSocketServer(client_manager=client_mgr,
                              json=utils.json,
                              logger=socketio_logger,
                              engineio_logger=socketio_logger,
                              async_handlers=False,
                              **server_options)

        realtime_services = create_realtime_handler(sio)
        rt_api.pubsub_listener.start(realtime_services)
        GLOBAL_SIO = sio

    return GLOBAL_SIO


def validate_event_filter(ef):
    if not isinstance(ef.get('text', ''), (str, bytes)):
        raise ValueError(
            'Event filter is invalid. value=%s', str(ef))
    return ef


def receipt_callback(trace_id, *args, **kwargs):
    client.pop_trace(trace_id)


AUTH_CHECK_SLEEP_TIME = getattr(settings, 'REALTIME_AUTH_TIMEOUT_SECONDS', 1.0)


def confirm_authorzation(sid, sios):

    extra = dict(sid=sid)
    logger.debug('Confirming auth for new socket connection (waiting %s seconds).',
                 AUTH_CHECK_SLEEP_TIME, extra=extra)
    eventlet.sleep(AUTH_CHECK_SLEEP_TIME)
    if not client.is_client(sid):
        logger.debug(
            "Disconnecting unauthenticated socket connection %s", sid, extra=extra)
        sios.disconnect(sid)
    else:
        logger.debug(
            'New socket connection is authenticated. sid=%s', sid, extra=extra)


CLIENT_CLEANUP_INTERVAL = 30  # seconds


def cleanup_disconnected_clients(sios):

    logger.info('Clean up disconnected sockets.')
    if not sios.environ:
        return

    environ = [sid for sid in sios.environ]
    client_list = set(client.get_client_list())

    remove_these_clients = set(
        [c for c in client_list if c.sid not in environ])

    if len(remove_these_clients) > 0:

        for c in remove_these_clients:
            logger.info('Cleaning up disconnected socket.', extra={
                        'sid': c.sid, 'username': c.username})

        client.remove_clients(
            *[x.sid for x in remove_these_clients])
    else:
        logger.debug('No sockets to clean up.')

    eventlet.spawn_after(CLIENT_CLEANUP_INTERVAL,
                         cleanup_disconnected_clients, sios)


def create_realtime_handler(sios):
    class RealtimeServices:

        supported_message_types = ['new_event', 'update_event', 'delete_event',
                                   'count_event', 'subject_position_update', 'service_status',
                                   'subjectstatus_update',
                                   ]

        @sios.on('connect', namespace='/')
        def on_connect(sid, socket, *args):
            # Drop the user if they don't authenticate immediately
            socket['authed'] = False

            logger.info('on_connect', extra={'sid': str(sid)})
            logger.debug('on_connect', extra={
                         'sid': str(sid), 'socket': repr(socket)})

            # Make sure the connection authenticates immediately
            eventlet.spawn(confirm_authorzation, sid, sios)

        @sios.on('disconnect')
        def on_disconnect(sid, *args):
            extra = dict(sid=sid)
            logger.info('Client disconnect %s', sid, extra=extra)
            client.remove_client(sid)

        @sios.on('authorization', namespace='/das')
        def on_authenticate(sid, data):
            try:
                # validate the data
                for param in ('type', 'authorization', 'id'):
                    if param not in data:
                        sios.emit('resp_authorization',
                                  {'resp_id': data['id'],
                                   'status': {'code': 400,
                                              'message': 'Required fields: "type", "authorization", "id"'}},
                                  room=str(sid),
                                  namespace='/das')
                        sios.disconnect(sid)

                # To authenticate the token, we need to create a fake http
                # request for oauth to authenticate
                request = DummyRequest(
                    headers={'Authorization': data['authorization']})
                user = authenticate(**{'request': request})
                # The token checks out
                if user is not None:
                    extra = dict(sid=sid, user_id=user.id)
                    logger.info(
                        'Socket sid=%s, user=%s authenticated successfully',
                        sid, user, extra=extra
                    )

                    # Put the user into redis
                    client_data = client.ClientData(
                        sid=sid, username=user.username, bbox=None)
                    client.add_client(sid, client_data)

                    # Put the connection into the correct rooms
                    sios.manager.enter_room(sid, 'all_clients', '/das')
                    sios.manager.enter_room(sid, sid, '/das')

                    # tell the user that they've been authenticated
                    sios.emit('resp_authorization',
                              {'type': 'resp_authorization', 'resp_id': data['id'],
                               'status': {'code': 200, 'message': 'OK'}},
                              room=str(sid),
                              namespace='/das')

                else:
                    extra = dict(sid=sid)
                    logger.warning(
                        'User is None, so disconnecting. sid=%s, data=%s',
                        sid, data, extra=extra)
                    sios.emit('resp_authorization',
                              {'type': 'resp_authorization',
                               'resp_id': data['id'],
                               'status': {'code': 401, 'message': 'Invalid credentials'}},
                              room=str(sid),
                              namespace='/das')

            except:
                sios.emit('resp_authorization',
                          {'type': 'resp_authorization',
                           'resp_id': data['id'],
                           'status': {'code': 401, 'message': 'Authentication error'}},
                          room=str(sid),
                          namespace='/das')
                logger.exception('Disconnecting session. data=%s', data)
                sios.disconnect(sid)

        @sios.on('bbox', namespace='/das')
        def on_bbox(sid, data):
            extra = dict(sid=sid, data=data)
            bbox = data['data']
            if bbox:
                bbox = bbox.split(',')
                bbox = [float(v) for v in bbox]
                if len(bbox) != 4:
                    raise ValueError("invalid bbox param")

            bbox = client.Bbox(*bbox)
            client.update_client(sid, bbox=bbox)
            sios.emit('bbox_resp',
                      {'type': 'bbox_resp',
                       'message': 'bbox saved.',
                       'bbox': bbox
                       },
                      room=str(sid),
                      namespace='/das')

        @sios.on('event_filter', namespace='/das')
        def on_event_filter(sid, event_filter):
            """
            This is expecting a dict containing custom filter attributes.

            :param event_filter: Event filter (Ex. {'text': 'arrest'}) can also be an empty dict.
            :return: None
            """
            try:
                event_filter = validate_event_filter(event_filter)
                client.update_client(sid, event_filter=event_filter)

                extra = dict(sid=sid, event_filter=event_filter)
                logger.info('on_event_filter', extra=extra)

                sios.emit('event_filter_response',
                          {
                              'message': 'Event filter has been saved.',
                              'filter': event_filter,
                          },
                          room=str(sid),
                          namespace='/das')
            except ValueError as ve:
                sios.emit('event_filter_response',
                          {
                              'message': 'Failed to set event_filter.',
                              'error': str(ve),
                          },
                          room=str(sid),
                          namespace='/das')

        @sios.on('echo', namespace='/das')
        def on_echo(sid, *args):
            sios.emit('echo_resp',
                      {'type': 'echo_resp',
                       'resp_id': 5,
                       'message': args[0]['data']},
                      room=str(sid),
                      namespace='/das')

        @staticmethod
        def emit(message_type, data, user=None):
            # user is the SID if set
            if user and user not in sios.environ:
                client.remove_client(user)
                # extra = dict(sid=user)
                logger.warning(
                    'Tried to send a message to a disconnected client.',
                    user, extra={'sid': user})
                return
            try:

                # Add trace ID to message. It will be sent back in callback.
                if isinstance(data, dict):
                    data['trace_id'] = f'trace-{user}-{time.time()}'
                    client.push_trace(data['trace_id'], data)

                if user is None:
                    sios.emit(message_type, data, namespace='/das',
                              callback=receipt_callback)
                else:
                    sios.emit(message_type, data, room=str(
                        user), namespace='/das', callback=receipt_callback)

            except Exception as ex:
                if user:
                    client.remove_client(user)
                logger.exception("Error emitting event over socket")

        @staticmethod
        def send_realtime_message(message_data):
            if message_data['type'] in RealtimeServices.supported_message_types:
                extra = dict(sid=message_data['sid'],
                             type=message_data['type'])
                logger.info('Sending realtime messsage to %s', message_data['sid'],
                            extra=extra)
                RealtimeServices.emit(message_type=message_data['type'],
                                      data=message_data['data'],
                                      user=message_data['sid'])
            else:
                logger.error('Realtime server received invalid message type: %s',
                             message_data['type'])

    # Start up recursive calls to clean up disconnected clients.
    eventlet.spawn_after(CLIENT_CLEANUP_INTERVAL,
                         cleanup_disconnected_clients, sios)

    return RealtimeServices


class RTMClient(View):
    template_name = 'rtmclient.html'

    def get(self, request, *args, **kwargs):
        return render(request,
                      self.template_name,
                      {})
