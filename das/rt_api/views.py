import logging

import eventlet
from django.shortcuts import render
from django.views.generic import View
from django.conf import settings
from socketio.kombu_manager import KombuManager
from socketio.server import Server
from django.contrib.auth import authenticate
from django.db import close_old_connections, connection

from rt_api.rest_api_interface.dummy_request import DummyRequest
from rt_api import client
import rt_api.pubsub_listener
import utils.json


logger = logging.getLogger('rt_api')

GLOBAL_SIO = None


def create_rt_socketio():
    global GLOBAL_SIO
    if GLOBAL_SIO:
        return GLOBAL_SIO

    client_mgr = KombuManager(url=settings.REALTIME_BROKER_URL,
                              transport_options=settings.REALTIME_BROKER_OPTIONS
                              )
    server_options = dict(async_mode=settings.ASYNC_MODE)
    server_options['cors_credentials'] = \
        getattr(settings, 'CORS_ALLOW_CREDENTIALS', False)

    if not getattr(settings, 'CORS_ORIGIN_ALLOW_ALL', False):
        server_options['cors_allowed_origins'] = \
            getattr(settings, 'CORS_ORIGIN_WHITELIST', None)

    sio = Server(client_manager=client_mgr,
                 json=utils.json,
                 logger=logger,
                 engineio_logger=logger,
                 async_handlers=False,
                 **server_options)

    realtime_services = create_realtime_handler(sio)
    rt_api.pubsub_listener.start(realtime_services)
    GLOBAL_SIO = sio
    return sio


def create_realtime_handler(sios):
    class RealtimeServices:

        supported_message_types = ['new_event', 'update_event', 'delete_event',
                                   'count_event', 'subject_position_update']

        @sios.on('connect', namespace='/')
        def on_connect(sid, socket, *args):
            # Drop the user if they don't authenticate immediately
            socket['authed'] = False

            def confirm_authed(sid, socket):
                logger.debug('confirming auth for sid=%s', sid)
                if not client.is_client(sid):
                    extra = dict(sid=sid)
                    logger.info(
                        "Disconnecting unauthenticated socket connection %s",
                        sid, extra=extra)
                    sios.disconnect(sid)

            # Make sure the connection authenticates immediately
            eventlet.spawn_after(settings.REALTIME_AUTH_TIMEOUT_SECONDS,
                                 confirm_authed, sid, socket)

            def cleanup():
                RealtimeServices.cleanup_disconnected_clients()

            # Kick off cleaning up old socket connections
            eventlet.spawn_after(settings.REALTIME_AUTH_TIMEOUT_SECONDS,
                                 cleanup())

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

                        logger.debug(
                            'Inside on_authenticate, disconnecting. params=%s', data)
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
                    # sios.disconnect(sid)

            except:
                sios.emit('resp_authorization',
                          {'type': 'resp_authorization',
                           'resp_id': data['id'],
                           'status': {'code': 401, 'message': 'Authentication error'}},
                          room=str(sid),
                          namespace='/das')
                logger.exception('Disconnecting session. data=%s', data)
                sios.disconnect(sid)
            finally:
                close_old_connections()

        @sios.on('bbox', namespace='/das')
        def on_bbox(sid, data):
            extra = dict(sid=sid, data=data)
            logger.info('on_bbox(data=%s)', data, extra=extra)
            bbox = data['data']
            if bbox:
                bbox = bbox.split(',')
                bbox = [float(v) for v in bbox]
                if len(bbox) != 4:
                    raise ValueError("invalid bbox param")
            logger.debug('RT socket set_bbox set= %s', bbox)

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
            def validate_event_filter(ef):
                if not isinstance(ef.get('text', ''), (str, bytes)):
                    raise ValueError(
                        'Event filter is invalid. value=%s', str(ef))
                return ef

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
                extra = dict(sid=user)
                logger.warning(
                    'Tried to send a message to a disconnected client. user=%s',
                    user, extra=extra)
                return
            try:
                if user is None:
                    sios.emit(message_type, data, namespace='/das')
                else:
                    sios.emit(message_type, data, room=str(
                        user), namespace='/das')

            except Exception as ex:
                if user:
                    client.remove_client(user)
                logger.exception("Error emitting event over socket")

        @staticmethod
        def send_realtime_message(message_data):
            extra = dict(data=message_data)
            logger.info('Sending realtime messsage, data=%s', message_data,
                        extra=extra)
            if message_data['type'] in RealtimeServices.supported_message_types:
                RealtimeServices.emit(message_data['type'],
                                      message_data['data'],
                                      message_data['sid'])
            else:
                logger.error('Realtime server received invalid message type: %s',
                             message_data['type'])

        @staticmethod
        def cleanup_disconnected_clients():
            """
            TODO make this manager aware,
            as this will not work for multiple rt servers running
            """
            if not sios.environ:
                return
            environ = [sid for sid in sios.environ]
            clients = list(client.get_client_list())
            for c in clients:
                if c.sid not in environ:
                    extra = dict(sid=c.sid, username=c.username)
                    logger.info('Cleaning up disconnected user: %s', c.username,
                                extra=extra)
                    client.remove_client(c.sid)

    return RealtimeServices


class RTMClient(View):
    template_name = 'rtmclient.html'

    def get(self, request, *args, **kwargs):
        return render(request,
                      self.template_name,
                      {})
