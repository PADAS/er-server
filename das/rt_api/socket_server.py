import logging
import time

import eventlet
from django.conf import settings
from django.db import close_old_connections
from django.contrib.auth import authenticate
from socketio.server import Server
from socketio.kombu_manager import KombuManager
from rt_api.client import remove_client, add_client, ClientData, Bbox, \
    update_client, message_index, push_trace

import utils.json
import rt_api.pubsub_listener
from rt_api.rest_api_interface.dummy_request import DummyRequest
from utils import stats

logger = logging.getLogger('rt_api')

GLOBAL_SIO = None
CLIENT_CLEANUP_INTERVAL = 30  # seconds


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


def connect_ack(sid, sios):

    logger.debug('Acknowledge connection for sid: %s', sid)
    eventlet.sleep(1.0)
    sios.emit('connect_ack', {
              'type': 'connect_ack', 'message': 'Connect acknowledgment.'}, room=str(sid), namespace='/das')


def create_realtime_handler(sios):
    class RealtimeServices:

        supported_message_types = ['new_event', 'update_event', 'delete_event',
                                   'count_event', 'service_status', 'subject_status', ]

        do_not_trace_these_types = ['service_status', ]

        @sios.on('connect', namespace='/')
        def on_connect(sid, socket, *args):
            # Drop the user if they don't authenticate immediately
            socket['authed'] = False

            logger.info('on_connect', extra={'sid': str(sid)})
            logger.debug('on_connect', extra={
                         'sid': str(sid), 'socket': repr(socket)})

            # Send a connect acknowledgment (helpful for troubleshooting).
            eventlet.spawn(connect_ack, sid, sios)

            # Make sure the connection authenticates immediately
            eventlet.spawn(confirm_authorzation, sid, sios)

        @sios.on('disconnect')
        def on_disconnect(sid, *args):
            extra = dict(sid=sid)
            logger.info('Client disconnect %s', sid, extra=extra)
            remove_client(sid)

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
                    client_data = ClientData(
                        sid=sid, username=user.username, bbox=None)
                    add_client(sid, client_data)

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

            bbox = Bbox(*bbox)
            update_client(sid, bbox=bbox)
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
                update_client(sid, event_filter=event_filter)

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
        def emit(message_type, data, socketid=None):
            # user is the SID if set
            if socketid and socketid not in sios.environ:
                remove_client(socketid)
                # extra = dict(sid=user)
                logger.warning(
                    'Tried to send a message to a disconnected client.', extra={'sid': socketid})
                return
            try:

                # Add a message index. The client can use this to identify gaps
                # in message streams.
                data['mid'] = message_index(socketid, message_type)

                # Add trace ID to message. It will be sent back in callback.
                if message_type not in RealtimeServices.do_not_trace_these_types \
                        and isinstance(data, dict):
                    data['trace_id'] = f'trace-{socketid}-{time.time()}'
                    push_trace(data['trace_id'], data)

                if socketid is None:
                    sios.emit(message_type, data, namespace='/das',
                              callback=receipt_callback)
                else:

                    # Sample 10% of realtime messages per message-type.
                    stats.increment(f'rt.emit.{message_type}', tags={'service': 'realtime'}, sample_rate=0.1)

                    sios.emit(message_type, data, room=str(
                        socketid), namespace='/das', callback=receipt_callback)

            except Exception as ex:
                if socketid:
                    remove_client(socketid)
                    logger.exception(
                        f"Error emitting event over socket {socketid}")
                else:
                    logger.exception(f"Error emitting event over socket")

        @staticmethod
        def send_realtime_message(message_data):
            if message_data['type'] in RealtimeServices.supported_message_types:
                extra = dict(sid=message_data['sid'],
                             type=message_data['type'])
                logger.info('Sending realtime messsage to %s', message_data['sid'],
                            extra=extra)
                RealtimeServices.emit(message_type=message_data['type'],
                                      data=message_data['data'],
                                      socketid=message_data['sid'])
            else:
                logger.error('Realtime server received invalid message type: %s',
                             message_data['type'])

    # Start up recursive calls to clean up disconnected clients.
    eventlet.spawn_after(CLIENT_CLEANUP_INTERVAL,
                         cleanup_disconnected_clients, sios)

    return RealtimeServices