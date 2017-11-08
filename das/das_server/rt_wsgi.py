"""
WSGI config for real-time das project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""
import os

import eventlet
eventlet.monkey_patch()

from django.core.wsgi import get_wsgi_application
from socketio import Middleware
from das_server.log import init_logging
from rt_api.views import create_rt_socketio


init_logging()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")

app = get_wsgi_application()
sio = create_rt_socketio()
application = Middleware(sio, app)
