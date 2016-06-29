"""
WSGI config for real-time das project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""
import os

import eventlet
eventlet.monkey_patch()
from das_server.log import init_logging
init_logging()


from django.core.wsgi import get_wsgi_application
import rt_api

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")


app = get_wsgi_application()
application = rt_api.sios.init_app(app).wsgi_app

