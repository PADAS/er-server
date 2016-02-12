import sys
import logging
import eventlet
from django.contrib.auth import authenticate
from oauthlib.common import Request
logger = logging.getLogger(__name__)


def create_realtime_handler(sios):

    class RealtimeServices():

        @sios.on('connect', namespace='/')
        def on_connect(sid, socket, *args):
            # Mark the connection as unauthenticated
            socket['user'] = None

            # Drop the connection if the client hasn't authenticated within one second
            def confirm_authed(sid, socket):
                if socket['user'] is None:
                    sios.server.disconnect(sid)

            eventlet.spawn_after(1.0, confirm_authed, sid, socket)

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

                # to authenticate the token, we need to create a fake http request for oauth to authenticate
                request = DummyRequest(headers={'Authorization': data['authorization']})
                user = authenticate(**{'request': request})

                # If the token checks out, mark the connection as authenticated and put it into the chat rooms
                if user is not None:
                    sios.server.environ[sid]['user'] = user
                    sios.server.manager.enter_room(sid, 'all_clients', '/das')
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
        def emit_subject_update(subjectid, geo_json=None, user=None):
            data = {'type': 'subject_position_update', 'subject_id': subjectid}
            if geo_json is not None:
                data['geo_json'] = geo_json
            RealtimeServices.emit('subject_position_update', data, user)

        @staticmethod
        def emit_new_event(event_id, event_data=None, user=None):
            data = {'type': 'new_event', 'event_id': event_id}
            if event_data is not None:
                data['event_data'] = event_data

            logger.info("Emitting new event. %s", event_data)
            RealtimeServices.emit('new_event', data, user)

        @staticmethod
        def emit(message_type, data, user=None):
            try:
                if user is None:
                    sios.emit(message_type, data, namespace='/das')
                else:
                    sios.emit(message_type, data, room=str(user), namespace='/das')
            except Exception as ex:

                logger.error("Error emitting event over socket", ex)

    return RealtimeServices

class DummyRequest(Request):
    _request = None
    def __init__(self, uri='/dummy', http_method='POST', body={}, headers=None, encoding='utf-8'):
        self.method = http_method
        self.META = headers
        self.POST = body
        self._request = self
        Request.__init__(self, uri, http_method, body, headers, encoding)

    def get_full_path(self):
        return self.uri

    def build_absolute_uri(self, url):
        return url