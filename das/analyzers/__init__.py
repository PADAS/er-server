import logging

from django.conf import settings
from das_server import celery

logger = logging.getLogger(__name__)

# Patch Celery's configuration with some attributes that Celery_once will
# use to control task creation.

celery.app.conf.ONCE = {
    'backend': 'celery_once.backends.Redis',
    'settings': {

        # Co-opt the URL for Celery to use for storing celery_once semaphores.
        'url': settings.CELERY_BROKER_URL,

        # three minutes, default expiration for a celery_once semaphore.
        'default_timeout': 60 * 3
    }
}
