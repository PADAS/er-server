import logging

import redis
from celery_once import QueueOnce

from django.conf import settings

import utils.tenant.providers
from das_server import celery

logger = logging.getLogger(__name__)


# This is a sentinel key that a livenessProbe will look for to determine health of celery beat.
CELERYBEAT_PULSE_SENTINEL_KEY = "celerybeat-pulse-sentinel"


@celery.app.task(base=QueueOnce, once={"graceful": True})
def celerybeat_pulse():
    """
    Set a sentinel key to expire in 120 seconds.
    :return: None
    """
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    redis_client.setex(CELERYBEAT_PULSE_SENTINEL_KEY, 120, "n/a")


@celery.app.task(bind=True, base=QueueOnce, once={"graceful": True})
def refresh_tenants_cache(self):
    """
    Refresh the tenant cache
    :return: None
    """
    try:
        utils.tenant.providers.refresh_tenants_cache()
    except Exception as ex:
        self.retry(exc=ex, retry_backoff=True)
