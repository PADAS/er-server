#!/usr/bin/env python
#this comes too late when using manage.py
#set environment variable EVENTLET_SHOULDPATCH=True
import eventlet
eventlet.monkey_patch()

import errno
import sys
import os
from datetime import datetime
import socket
import socketio

from django.conf import settings
import django.core.management.commands.runserver as runserver
from django.utils import autoreload, six
from django.utils.encoding import force_text, get_system_encoding

import rt_api.server
import rt_api.pubsub_listener


class Command(runserver.Command):
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

        try:
            app = self.get_handler(*args, **options)
            socketio_app = rt_api.server.sios
            app = socketio_app.init_app(app=app, **{'message_queue': settings.REALTIME_BROKER_URL}).wsgi_app

            self.run_socket(self.addr, int(self.port), app,
                ipv6=self.use_ipv6, threading=threading)
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
            self.stderr.write("Error: %s" % error_text)
            # Need to use an OS exit because sys.exit doesn't work in a thread
            os._exit(1)
        except KeyboardInterrupt:
            if shutdown_message:
                self.stdout.write(shutdown_message)
            sys.exit(0)

    def run_socket(self, addr, port, app, ipv6=False, threading=False):
        import eventlet.wsgi
        eventlet.wsgi.server(eventlet.listen((addr, port)), app)




