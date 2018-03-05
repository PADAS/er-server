import json

from datetime import datetime, timedelta
import pytz
import dateutil.parser as dp

from django.conf import settings
import redis
from das_server import celery

from observations.models import SourceProvider

SERVICE_STATUS_NS = 'das-service-status'
SERVICE_STATUS_KEY_PATTERN = ':'.join((SERVICE_STATUS_NS, '{provider_key}'))


def store_service_status(provider_key=None, data=None):

    key = SERVICE_STATUS_KEY_PATTERN.format(provider_key=provider_key)
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    data['provider_key'] = provider_key

    redis_client.set(key, json.dumps(data))

    celery.app.send_task('rt_api.tasks.broadcast_service_status')


def get_service_status(provider_key=None):

    key = SERVICE_STATUS_KEY_PATTERN.format(provider_key=provider_key)
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)

    data = redis_client.get(key)
    if data:
        return _add_status_indicators(json.loads(data.decode('utf8')))


def _add_status_indicators(service_status):

    provider_key = service_status.get('provider_key')
    try:
        display_name = SourceProvider.objects.get(
            provider_key=provider_key).display_name
    except SourceProvider.DoesNotExist:
        display_name = provider_key

    service_status['display_name'] = display_name

    service_status['status_code'] = calculate_status_code(service_status)

    # These are hacks, but should be built to identify asset type (ie. Radio
    # vs. Collar vs. Airplane)
    service_status['system_status_title'] = 'System Activity'
    service_status['asset_status_title'] = 'Radio Activity'

    return service_status


ERROR_THRESHOLD = timedelta(minutes=10)
WARNING_THRESHOLD = timedelta(minutes=2)


def calculate_status_code(service_status):

    try:
        is_connected = service_status['datasource']['connected']
    except:
        is_connected = False

    try:
        connection_age = datetime.now(
            tz=pytz.utc) - dp.parse(service_status['datasource']['connection_changed_at'])
    except:
        connection_age = None

    try:
        heartbeat_age = datetime.now(
            tz=pytz.utc) - dp.parse(service_status['heartbeat']['latest_at'])
    except:
        heartbeat_age = None

    # Error thresholds
    if any(
        (heartbeat_age > ERROR_THRESHOLD, is_connected ==
         False and connection_age > ERROR_THRESHOLD),
    ):
        return 'ERROR'

    # Warning thresholds
    if any((
            heartbeat_age > WARNING_THRESHOLD, is_connected == False),
           ):
        return 'WARNING'

    return 'OK'


def get_source_provider_statuses():

    pattern = SERVICE_STATUS_KEY_PATTERN.format(provider_key='*')
    r = redis.from_url(settings.CELERY_BROKER_URL)

    # Build a dictionary for all the services that exist in the cache.
    provider_statuses = [json.loads(r.get(k).decode('utf8'))
                         for k in r.keys(pattern)]

    provider_statuses = [_add_status_indicators(s) for s in provider_statuses]

    return provider_statuses
