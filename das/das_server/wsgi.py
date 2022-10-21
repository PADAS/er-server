"""
WSGI config for das project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application

from das_server.log import init_logging
init_logging()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")

application = get_wsgi_application()
