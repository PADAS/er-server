
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

        @sios.on('disconnect', namespace='/')
        def on_disconnect(sid, *args):
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
                    # TODO: handle expiration better
                    redis_client.expire('realtime_connection', 300)  # 5 minutes

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
        def emit_subject_update(subjectid, geo_json=None, user=None, state=None):
            data = {'type': 'subject_position_update', 'subject_id': subjectid}
            if geo_json is not None:
                data['geo_json'] = geo_json
            if state is not None:
                data['state'] = state
            return RealtimeServices.emit('subject_position_update', data, user)

        @staticmethod
        def emit_new_event(event_id, event_data=None, user=None):
            data = {'type': 'new_event', 'event_id': event_id}
            if event_data is not None:
                data['event_data'] = event_data

            logger.info("Emitting new event. %s", event_id)
            return RealtimeServices.emit('new_event', data, user)

        @staticmethod
        def emit_update_event(event_id, event_data=None, user=None):
            data = {'type': 'update_event', 'event_id': event_id}
            if event_data is not None:
                data['event_data'] = event_data

            logger.info("Emitting update event. %s", event_id)
            return RealtimeServices.emit('update_event', data, user)

        @staticmethod
        def emit_delete_event(event_id, event_data=None, user=None):
            data = {'type': 'delete_event', 'event_id': event_id}
            logger.info("Emitting delete event. %s", event_id)
            return RealtimeServices.emit('delete_event', data, user)

        @staticmethod
        def emit_count_event(count, user=None):
            data = {'type': 'count_event', 'count': count}
            logger.info("Emitting count event change. %s", count)
            return RealtimeServices.emit('count_event', data, user)

        @staticmethod
        def emit(message_type, data, user=None):
            try:
                if user is None:
                    sios.emit(message_type, data, namespace='/das')
                elif user in sios.server.environ:
                    sios.emit(message_type, data, room=str(user), namespace='/das')
                else:
                    return False

                return True

            except Exception as ex:
                logger.error("Error emitting event over socket", ex)

            return False

    return RealtimeServices
