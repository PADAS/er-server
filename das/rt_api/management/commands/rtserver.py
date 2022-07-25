from __future__ import unicode_literals

import atexit
import errno
import logging
import os
import socket
import sys
from datetime import datetime

import six

from django.conf import settings
from django.core.management.commands.runserver import Command as RunCommand
from django.core.management.commands.runserver import run
from django.db import close_old_connections
from django.utils import autoreload
from django.utils.encoding import get_system_encoding

import rt_api.client as client
from rt_api.views import create_rt_socketio

# this comes too late when using manage.py
# set environment variable EVENTLET_SHOULDPATCH=True
# eventlet.monkey_patch()


logger = logging.getLogger('rt_api')

# allow 50 or so socket connections
MAX_GREEN_THREADS = 50


class Command(RunCommand):
    help = 'Run the DAS Socket.IO server'

    def inner_run(self, *args, **options):

        # If an exception was silenced in ManagementUtility.execute in order
        # to be raised in the child process, raise it now.
        autoreload.raise_last_exception()

        threading = options.get('use_threading')
        shutdown_message = options.get('shutdown_message', '')
        quit_command = 'CTRL-BREAK' if sys.platform == 'win32' else 'CONTROL-C'

        self.stdout.write("Performing system checks...\n\n")
        self.check(display_num_errors=True)
        self.check_migrations()
        now = datetime.now().strftime('%B %d, %Y - %X')
        if six.PY2:
            now = now.decode(get_system_encoding())
        self.stdout.write(now)
        self.stdout.write((
            "Django version %(version)s, using settings %(settings)r\n"
            "Starting development server at http://%(addr)s:%(port)s/\n"
            "Quit the server with %(quit_command)s.\n"
        ) % {
            "version": self.get_version(),
            "settings": settings.SETTINGS_MODULE,
            "addr": '[%s]' % self.addr if self._raw_ipv6 else self.addr,
            "port": self.port,
            "quit_command": quit_command,
        })

        close_old_connections()

        client.init_redis_storage()
        client.start_trace_consumer()

        # shutdown hook to clean up service keys on service exit
        atexit.register(client.shutdown_cleanup)

        try:
            sio = create_rt_socketio()
            if sio.async_mode == 'threading':
                handler = self.get_handler(*args, **options)
                run(self.addr, int(self.port), handler,
                    ipv6=self.use_ipv6, threading=threading)
            elif sio.async_mode == 'eventlet':
                # deploy with eventlet
                import eventlet
                import eventlet.wsgi

                from das_server.rt_wsgi import application
                eventlet.wsgi.server(eventlet.listen((self.addr, int(self.port))),
                                     application,
                                     max_size=MAX_GREEN_THREADS)
            elif sio.async_mode == 'gevent':
                # deploy with gevent
                from gevent import pywsgi

                from das_server.rt_wsgi import application
                try:
                    from geventwebsocket.handler import WebSocketHandler
                    websocket = True
                except ImportError:
                    websocket = False
                if websocket:
                    pywsgi.WSGIServer(
                        ('', 8000), application,
                        handler_class=WebSocketHandler).serve_forever()
                else:
                    pywsgi.WSGIServer((self.addr, int(self.port)),
                                      application).serve_forever()
            elif sio.async_mode == 'gevent_uwsgi':
                logger.info(
                    'Start the application through the uwsgi server. Example:')
                logger.info('uwsgi --http :5000 --gevent 1000 --http-websockets '
                            '--master --wsgi-file django_example/wsgi.py --callable '
                            'application')
            else:
                logger.info('Unknown async_mode: ' + sio.async_mode)

        except socket.error as e:
            # Use helpful error messages instead of ugly tracebacks.
            ERRORS = {
                errno.EACCES: "You don't have permission to access that port.",
                errno.EADDRINUSE: "That port is already in use.",
                errno.EADDRNOTAVAIL: "That IP address can't be assigned to.",
            }
            try:
                error_text = ERRORS[e.errno]
            except KeyError:
                error_text = force_str(e)
            self.stderr.write("Error: %s" % error_text)
            # Need to use an OS exit because sys.exit doesn't work in a thread
            os._exit(1)
        except KeyboardInterrupt:
            if shutdown_message:
                self.stdout.write(shutdown_message)
            sys.exit(0)
        finally:
            client.stop_trace_consumer()
