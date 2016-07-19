from __future__ import unicode_literals

# this comes too late when using manage.py
# set environment variable EVENTLET_SHOULDPATCH=True
# eventlet.monkey_patch()

import errno
import sys
import os
import socket
import logging

from django.conf import settings
import django.core.management.commands.runserver as runserver
from django.utils import autoreload
from django.utils.encoding import force_text
import eventlet

import utils.json
import rt_api.server
from rt_api.socketio import RTSocketIO
import rt_api.pubsub_listener

logger = logging.getLogger('rt_api')

MAX_GREEN_THREADS = 20


class Command(runserver.Command):

    def inner_run(self, *args, **options):
        # If an exception was silenced in ManagementUtility.execute in order
        # to be raised in the child process, raise it now.
        autoreload.raise_last_exception()

        try:
            wsgi_handler = self.get_handler(*args, **options)
            sios = RTSocketIO(app=wsgi_handler,
                              message_queue=settings.REALTIME_BROKER_URL,
                              json=utils.json,
                              logger=logger,
                              engineio_logger=logger)
            realtime_services = rt_api.server.create_realtime_handler(sios)
            rt_api.pubsub_listener.start(realtime_services)
            self.run_socket(self.addr, int(self.port), sios.wsgi_app)

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
                error_text = force_text(e)
            message = 'Error: %s' % error_text
            logger.error(message)
            self.stderr.write(message)
            # Need to use an, OS exit because sys.exit doesn't work in a thread
            os._exit(1)
        except KeyboardInterrupt:
            sys.exit(0)


    def run_socket(self, addr, port, app):
        eventlet.wsgi.server(eventlet.listen((addr, port)),
                             app, max_size=MAX_GREEN_THREADS)




