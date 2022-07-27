"""
WSGI config for real-time das project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""
import os

from gevent import monkey
from socketio import WSGIApp

from django.core.wsgi import get_wsgi_application

from das_server.log import init_logging
from rt_api.views import create_rt_socketio

monkey.patch_all()


init_logging()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")
app = get_wsgi_application()

sio = create_rt_socketio()
application = WSGIApp(sio, app)
