"""
WSGI config for real-time das project.
It exposes the WSGI callable as a module-level variable named ``application``.
For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""
import os

import eventlet.patcher

if not eventlet.patcher.is_monkey_patched(os):
    print("Error, eventlet not monkey patched during import rt_wsgi!!")

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from socketio import WSGIApp
from das_server.log import init_logging
from utils.tenant.providers import post_tenant_to_thread

post_tenant_to_thread(domain=getattr(settings, "SERVER_FQDN", None))
init_logging()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")
app = get_wsgi_application()

from rt_api.views import create_rt_socketio

sio = create_rt_socketio()
application = WSGIApp(sio, app)
