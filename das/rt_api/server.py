
import eventlet
import json
import logging
import redis

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import close_old_connections
from rt_api.rest_api_interface.dummy_request import DummyRequest

logger = logging.getLogger(__name__)
redis_client = redis.from_url(settings.REALTIME_BROKER_URL)

def create_realtime_handler(sios):

    class RealtimeServices():

        supported_message_types = ['new_event', 'update_event', 'delete_event',
                                   'count_event', 'subject_position_update']

        @sios.on('connect', namespace='/')
        def on_connect(sid, socket, *args):
            # Drop the user if they don't authenticate immediately
            socket['authed'] = False
            def confirm_authed(sid, socket):
                if not redis_client.hexists('realtime_connections', str(sid)):
                    logger.info("Disconnecting unauthenticated socket connection")
                    sios.server.disconnect(sid)

            # Make sure the connection authenticates immediately
            eventlet.spawn_after(settings.REALTIME_AUTH_TIMEOUT_SECONDS,
                                 confirm_authed, sid, socket)

        @sios.on('disconnect')
        def on_disconnect(sid, *args):
            logger.debug('Got a disconnection event from {0}'.format(str(sid)))
            redis_client.hdel('realtime_connections', str(sid))

        @sios.on('authorization', namespace='/das')
        def on_authenticate(sid, data):
            try:
                # validate the data
                for param in ('type', 'authorization', 'id'):
                    if param not in data:
                        sios.emit('resp_authorization',
                                  {'resp_id': data['id'],
                                       'status': {'code': 400, 'message': 'Required fields: "type", "authorization", "id"'}},
                                  room=str(sid),
                                  namespace='/das')
                        sios.server.disconnect(sid)

                # To authenticate the token, we need to create a fake http request for oauth to authenticate
                request = DummyRequest(headers={'Authorization': data['authorization']})
                user = authenticate(**{'request': request})

                # The token checks out
                if user is not None:
                    logger.info("Socket {0} user authenticted successfully".format(sid))

                    # Put the user into redis
                    redis_client.hset('realtime_connections', str(sid), user.username)

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
                    sios.emit('resp_authorization',
                              {'type': 'resp_authorization',
                               'resp_id': data['id'],
                               'status': {'code': 401, 'message': 'Invalid credentials'}},
                              room=str(sid),
                              namespace='/das')
                    sios.server.disconnect(sid)

            except:
                sios.emit('resp_authorization',
                          {'type': 'resp_authorization',
                           'resp_id': data['id'],
                           'status': {'code': 401, 'message': 'Authentication error'}},
                          room=str(sid),
                          namespace='/das')
                sios.server.disconnect(sid)
            finally:
                close_old_connections()


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
            logger.error('RT socket error in root namespace', e)

        @sios.on_error(namespace='/das')
        def on_das_error(e):
            logger.error('RT socket error in das namespace', e)

        @sios.on_error_default  # handles all namespaces without an explicit error handler
        def default_error_handler(e):
            logger.error('RT socket error', e)


        @staticmethod
        def emit(message_type, data, user=None):
            if user not in sios.server.environ:
                redis_client.hdel('realtime_connections', str(user))
                logger.warn('Tried to send a message to a disconnected client: {0}'.format(str(user)))
                return
            try:
                if user is None:
                    sios.emit(message_type, data, namespace='/das')
                else:
                    sios.emit(message_type, data, room=str(user), namespace='/das')

            except Exception as ex:
                redis_client.hdel('realtime_connections', str(user))
                logger.error("Error emitting event over socket", ex)

        @staticmethod
        def send_realtime_message(message_data):
            if message_data['type'] in RealtimeServices.supported_message_types:
                RealtimeServices.emit(message_data['type'],
                                      message_data['data'],
                                      message_data['sid'])
            else:
                logger.error('Realtime server received invald message type',
                             message_data['type'])

    return RealtimeServices
