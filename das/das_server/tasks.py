import logging

import redis
from celery_once import QueueOnce

from django.conf import settings
from django.core.management import call_command

from das_server import celery

logger = logging.getLogger(__name__)


@celery.app.task()
def publish_daily_site_metrics():
    call_command("site_metrics")


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
