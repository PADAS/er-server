import sys
import logging
import socketio
import threading
from django.conf import settings
from django.contrib.auth import authenticate
from oauthlib.common import Request
from das_server import pubsub
from observations.models import Subject
from observations.serializers import ObservationSerializer
logger = logging.getLogger(__name__)


class _SocketIOMiddleware(socketio.Middleware):
    """This WSGI middleware simply exposes the Flask application in the WSGI
    environment before executing the request.
    """

    def __init__(self, socketio_app, django_app, socketio_path='socket.io'):
        self.django_app = django_app
        super(_SocketIOMiddleware, self).__init__(socketio_app,
                                                  django_app,
                                                  socketio_path)

    def __call__(self, environ, start_response):
        environ['django.app'] = self.django_app
        return super(_SocketIOMiddleware, self).__call__(environ, start_response)


class RTSocketIO(object):
    """Create a SocketIO server.
    :param app: The flask application instance. If the application instance
                isn't known at the time this class is instantiated, then call
                ``socketio.init_app(app)`` once the application instance is
                available.
    :param message_queue: A connection URL for a message queue service the
                          server can use for multi-process communication. A
                          message queue is not required when using a single
                          server process.
    :param resource: The SocketIO resource name. Defaults to ``'socket.io'``.
                     Leave this as is unless you know what you are doing.
    :param kwargs: Socket.IO and Engine.IO server options.

    The Socket.IO server options are detailed below:

    :param client_manager: The client manager instance that will manage the
                           client list. When this is omitted, the client list
                           is stored in an in-memory structure, so the use of
                           multiple connected servers is not possible. In most
                           cases, this argument does not need to be set
                           explicitly.
    :param logger: To enable logging set to ``True`` or pass a logger object to
                   use. To disable logging set to ``False``.
    :param binary: ``True`` to support binary payloads, ``False`` to treat all
                   payloads as text. On Python 2, if this is set to ``True``,
                   ``unicode`` values are treated as text, and ``str`` and
                   ``bytes`` values are treated as binary.  This option has no
                   effect on Python 3, where text and binary payloads are
                   always automatically discovered.
    :param json: An alternative json module to use for encoding and decoding
                 packets. Custom json modules must have ``dumps`` and ``loads``
                 functions that are compatible with the standard library
                 versions.

    The Engine.IO server configuration supports the following settings:

    :param async_mode: The library used for asynchronous operations. Valid
                       options are "threading", "eventlet" and "gevent". If
                       this argument is not given, "eventlet" is tried first,
                       then "gevent", and finally "threading". The websocket
                       transport is not supported in "ithreading" mode.
    :param ping_timeout: The time in seconds that the client waits for the
                         server to respond before disconnecting.
    :param ping_interval: The interval in seconds at which the client pings
                          the server.
    :param max_http_buffer_size: The maximum size of a message when using the
                                 polling transport.
    :param allow_upgrades: Whether to allow transport upgrades or not.
    :param http_compression: Whether to compress packages when using the
                             polling transport.
    :param compression_threshold: Only compress messages when their byte size
                                  is greater than this value.
    :param cookie: Name of the HTTP cookie that contains the client session
                   id. If set to ``None``, a cookie is not sent to the client.
    :param cors_allowed_origins: List of origins that are allowed to connect
                                 to this server. All origins are allowed by
                                 default.
    :param cors_credentials: Whether credentials (cookies, authentication) are
                             allowed in requests to this server.
    :param engineio_logger: To enable Engine.IO logging set to ``True`` or pass
                            a logger object to use. To disable logging set to
                            ``False``.
    """

    def __init__(self, app=None, **kwargs):
        self.server = None
        self.wsgi_app = None
        self.server_options = None
        self.handlers = []
        self.exception_handlers = {}
        self.default_exception_handler = None
        if app is not None:
            self.init_app(app, **kwargs)

    def init_app(self, app, **kwargs):
        if not hasattr(app, 'extensions'):
            app.extensions = {}  # pragma: no cover
        app.extensions['socketio'] = self
        self.server_options = kwargs

        if 'client_manager' not in self.server_options:
            url = kwargs.pop('message_queue', None)
            if url:
                queue = socketio.KombuManager(url)
                self.server_options['client_manager'] = queue
        if ('cors_credentials' not in kwargs and
            hasattr(settings, 'CORS_CREDENTIALS')):
            self.server_options['cors_credentials'] = settings.CORS_CREDENTIALS

        if 'async_mode' not in kwargs:
            kwargs['async_mode'] = settings.ASYNC_MODE

        resource = kwargs.pop('resource', 'socket.io')
        if resource.startswith('/'):
            resource = resource[1:]
        self.server = socketio.Server(**self.server_options)
        for handler in self.handlers:
            self.server.on(handler[0], handler[1], namespace=handler[2])
        self.wsgi_app = _SocketIOMiddleware(self.server, app,
                                           socketio_path=resource)
        return self

    def on(self, message, namespace=None):
        """Decorator to register a SocketIO event handler.

        This decorator must be applied to SocketIO event handlers. Example::

            @socketio.on('my event', namespace='/chat')
            def handle_my_custom_event(sid, json):
                print('received json: ' + str(json))

        :param message: The name of the event. This is normally a user defined
                        string, but a few event names are already defined. Use
                        ``'message'`` to define a handler that takes a string
                        payload, ``'json'`` to define a handler that takes a
                        JSON blob payload, ``'connect'`` or ``'disconnect'``
                        to create handlers for connection and disconnection
                        events.
        :param namespace: The namespace on which the handler is to be
                          registered. Defaults to the global namespace.
        """
        namespace = namespace or '/'

        def decorator(handler):
            def _handler(sid, *args):
                app = self.server.environ[sid]['django.app']
                try:
                    ret = handler(sid, *args)
                except:
                    err_handler = self.exception_handlers.get(
                        namespace, self.default_exception_handler)
                    if err_handler is None:
                        raise
                    type, value, traceback = sys.exc_info()
                    return err_handler(value)
                return ret

            if self.server:
                self.server.on(message, _handler, namespace=namespace)
            else:
                self.handlers.append((message, _handler, namespace))
            return _handler

        return decorator

    def on_error(self, namespace=None):
        """Decorator to define a custom error handler for SocketIO events.

        This decorator can be applied to a function that acts as an error
        handler for a namespace. This handler will be invoked when a SocketIO
        event handler raises an exception. The handler function must accept one
        argument, which is the exception raised. Example::

            @socketio.on_error(namespace='/chat')
            def chat_error_handler(e):
                print('An error has occurred: ' + str(e))

        :param namespace: The namespace for which to register the error
                          handler. Defaults to the global namespace.
        """
        namespace = namespace or '/'

        def decorator(exception_handler):
            if not callable(exception_handler):
                raise ValueError('exception_handler must be callable')
            self.exception_handlers[namespace] = exception_handler
            return exception_handler

        return decorator

    def on_error_default(self, exception_handler):
        """Decorator to define a default error handler for SocketIO events.

        This decorator can be applied to a function that acts as a default
        error handler for any namespaces that do not have a specific handler.
        Example::

            @socketio.on_error_default
            def error_handler(e):
                print('An error has occurred: ' + str(e))
        """
        if not callable(exception_handler):
            raise ValueError('exception_handler must be callable')
        self.default_exception_handler = exception_handler
        return exception_handler

    def emit(self, event, *args, **kwargs):
        """Emit a server generated SocketIO event.

        This function emits a SocketIO event to one or more connected clients.
        A JSON blob can be attached to the event as payload. This function can
        be used outside of a SocketIO event context, so it is appropriate to
        use when the server is the originator of an event, outside of any
        client context, such as in a regular HTTP request handler or a
        background task. Example::

            @app.route('/ping')
            def ping():
                socketio.emit('ping event', {'data': 42}, namespace='/chat')

        :param event: The name of the user event to emit.
        :param args: A dictionary with the JSON data to send as payload.
        :param namespace: The namespace under which the message is to be sent.
                          Defaults to the global namespace.
        :param room: Send the message to all the users in the given room. If
                     this parameter is not included, the event is sent to
                     all connected users.
        :param skip_sid: The session ID of a client to skip when broadcasting
                         to a room or to all clients. This can be used to
                         prevent a message from being sent to the sender.
        :param callback: If given, this function will be called to acknowledge
                         that the client has received the message. The
                         arguments that will be passed to the function are
                         those provided by the client. Callback functions can
                         only be used when addressing an individual client.
        """
        self.server.emit(event, *args, namespace=kwargs.get('namespace', '/'),
                         room=kwargs.get('room'), skip_sid=kwargs.get('skip_id'),
                         callback=kwargs.get('callback'))

    def send(self, data, json=False, namespace=None, room=None,
             callback=None, skip_sid=None):
        """Send a server-generated SocketIO message.

        This function sends a simple SocketIO message to one or more connected
        clients. The message can be a string or a JSON blob. This is a simpler
        version of ``emit()``, which should be preferred. This function can be
        used outside of a SocketIO event context, so it is appropriate to use
        when the server is the originator of an event.

        :param message: The message to send, either a string or a JSON blob.
        :param json: ``True`` if ``message`` is a JSON blob, ``False``
                     otherwise.
        :param namespace: The namespace under which the message is to be sent.
                          Defaults to the global namespace.
        :param room: Send the message only to the users in the given room. If
                     this parameter is not included, the message is sent to
                     all connected users.
        :param skip_sid: The session ID of a client to skip when broadcasting
                         to a room or to all clients. This can be used to
                         prevent a message from being sent to the sender.
        :param callback: If given, this function will be called to acknowledge
                         that the client has received the message. The
                         arguments that will be passed to the function are
                         those provided by the client. Callback functions can
                         only be used when addressing an individual client.
        """
        if json:
            self.emit('json', data, namespace=namespace, room=room,
                      skip_sid=skip_sid, callback=callback)
        else:
            self.emit('message', data, namespace=namespace, room=room,
                      skip_sid=skip_sid, callback=callback)

    def close_room(self, room, namespace=None):
        """Close a room.

        This function removes any users that are in the given room and then
        deletes the room from the server. This function can be used outside
        of a SocketIO event context.

        :param room: The name of the room to close.
        :param namespace: The namespace under which the room exists. Defaults
                          to the global namespace.
        """
        self.server.close_room(room, namespace)

    def test_client(self, app, namespace=None):
        """Return a simple SocketIO client that can be used for unit tests."""
        # return SocketIOTestClient(app, self, namespace)
        raise NotImplementedError()

    def _copy_session(self, src, dest):
        for k in src:
            dest[k] = src[k]


sios = RTSocketIO()


class RTServer(object):

    @sios.on('connect', namespace='/')
    def on_connect(sid, socket, *args):
        # Mark the connection as unauthenticated
        socket['user'] = None

        # Drop the connection if the client hasn't authenticated within one second
        def confirm_authed(sid, socket):
            if socket['user'] is None:
                sios.server.disconnect(sid)

        threading.Timer(1.0, confirm_authed, [sid, socket]).start()

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

    @staticmethod
    def user_subject_update(user, subjectid, observation):
        print('Emitting subject update to user')
        # Need to lookup the user's socket id
        sios.emit('subject_update', {'type': 'subject_update', 'subject_id': subjectid, 'observation': observation},
                  room=str(user), namespace='/das')
    @staticmethod
    def broadcast_subject_update(subjectid, observation):
        print('Broadcast subject update to all users')
        sios.emit('subject_update', {'type': 'subject_update', 'subject_id': subjectid, 'observation': observation},
                  namespace='/das')

    test = False
    if test:
        import rt_api.tests.subject_update_loop


class DummyRequest(Request):
    def __init__(self, uri='/dummy', http_method='POST', body={}, headers=None, encoding='utf-8'):
        self.method = http_method
        self.META = headers
        self.POST = body
        Request.__init__(self, uri, http_method, body, headers, encoding)

    def get_full_path(self):
        return self.uri