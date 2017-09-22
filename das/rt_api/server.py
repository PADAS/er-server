import eventlet
import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import close_old_connections, connection
from rt_api.rest_api_interface.dummy_request import DummyRequest

from rt_api import client


logger = logging.getLogger(__name__)


def create_realtime_handler(sios):
    class RealtimeServices():

        supported_message_types = ['new_event', 'update_event', 'delete_event',
                                   'count_event', 'subject_position_update']

        @sios.on('connect', namespace='/')
        def on_connect(sid, socket, *args):
            # Drop the user if they don't authenticate immediately
            socket['authed'] = False

            def confirm_authed(sid, socket):
                logger.debug('confirming auth for sid=%s', sid)
                if not client.is_client(sid):
                    logger.info(
                        "Disconnecting unauthenticated socket connection")
                    sios.server.disconnect(sid)

            # Make sure the connection authenticates immediately
            eventlet.spawn_after(settings.REALTIME_AUTH_TIMEOUT_SECONDS,
                                 confirm_authed, sid, socket)

        @sios.on('disconnect')
        def on_disconnect(sid, *args):
            logger.debug('Got a disconnection event from %s', sid)
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
                        sios.server.disconnect(sid)

                # To authenticate the token, we need to create a fake http
                # request for oauth to authenticate
                request = DummyRequest(
                    headers={'Authorization': data['authorization']})
                user = authenticate(**{'request': request})
                # The token checks out
                if user is not None:
                    logger.info(
                        'Socket sid=%s, user=%s authenticated successfully', sid, user)

                    # Put the user into redis
                    client_data = client.ClientData(
                        sid=sid, username=user.username, bbox=None)
                    client.add_client(sid, client_data)

                    # Put the connection into the correct rooms
                    sios.server.manager.enter_room(sid, 'all_clients', '/das')
                    sios.server.manager.enter_room(sid, sid, '/das')

                    # tell the user that they've been authenticated
                    sios.emit('resp_authorization',
                              {'type': 'resp_authorization', 'resp_id': data['id'],
                               'status': {'code': 200, 'message': 'OK'}},
                              room=str(sid),
                              namespace='/das')

                else:
                    logger.warning(
                        'User is None, so disconnecting. sid=%s, data=%s', sid, data)
                    sios.emit('resp_authorization',
                              {'type': 'resp_authorization',
                               'resp_id': data['id'],
                               'status': {'code': 401, 'message': 'Invalid credentials'}},
                              room=str(sid),
                              namespace='/das')
                    # sios.server.disconnect(sid)

            except:
                sios.emit('resp_authorization',
                          {'type': 'resp_authorization',
                           'resp_id': data['id'],
                           'status': {'code': 401, 'message': 'Authentication error'}},
                          room=str(sid),
                          namespace='/das')
                logger.exception('Disconnecting session. data=%s', data)
                sios.server.disconnect(sid)
            finally:
                close_old_connections()

        @sios.on('bbox', namespace='/das')
        def on_bbox(sid, data):
            logger.info('on_bbox(data=%s', data)
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
            '''
            This is expecting a dict containing custom filter attributes.

            :param event_filter: Event filter (Ex. {'text': 'arrest'}) can also be an empty dict.
            :return: None
            '''
            logger.info('event_filter data: %s', event_filter)

            def validate_event_filter(ef):
                if not isinstance(ef.get('text', ''), (str, bytes)):
                    raise ValueError(
                        'Event filter is invalid. value=%s', str(ef))
                return ef

            try:
                event_filter = validate_event_filter(event_filter)

                client.update_client(sid, event_filter=event_filter)
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

        @sios.on_error(namespace='/')
        def on_root_error(e):
            logger.error('Realtime / unhandled error. error=%s', e)

        @sios.on_error(namespace='/das')
        def on_das_error(e):
            logger.error('Realtime /das unhandled error. error=%s', e)

        @sios.on_error_default  # handles all namespaces without an explicit error handler
        def default_error_handler(e):
            logger.error('Realtime unhandled error. error=%s', e)

        @staticmethod
        def emit(message_type, data, user=None):
            if user not in sios.server.environ:
                client.remove_client(user)
                logger.warning(
                    'Tried to send a message to a disconnected client. user=%s', user)
                return
            try:
                if user is None:
                    sios.emit(message_type, data, namespace='/das')
                else:
                    sios.emit(message_type, data, room=str(
                        user), namespace='/das')

            except Exception as ex:
                client.remove_client(user)
                logger.error("Error emitting event over socket", ex)

        @staticmethod
        def send_realtime_message(message_data):
            logger.info('Sending realtime messsage, data=%s', message_data)
            if message_data['type'] in RealtimeServices.supported_message_types:
                RealtimeServices.emit(message_data['type'],
                                      message_data['data'],
                                      message_data['sid'])
            else:
                logger.error('Realtime server received invald message type',
                             message_data['type'])

    return RealtimeServices
