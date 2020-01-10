import logging

from django.core.management import call_command

from das_server import celery, pubsub

logger = logging.getLogger(__name__)


@celery.app.task()
def publish_daily_site_metrics():
    call_command('site_metrics')
