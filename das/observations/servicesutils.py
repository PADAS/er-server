import json
from datetime import datetime, timedelta

import dateutil.parser as dp
import pytz
import redis

from django.conf import settings
from django.contrib.postgres.fields import jsonb
from django.core.cache import cache
from django.db.models import Q

from das_server import celery
from observations.models import SourceProvider

SERVICE_STATUS_NS = 'das-service-status'
SERVICE_STATUS_KEY_PATTERN = ':'.join((SERVICE_STATUS_NS, '{provider_key}'))
SOURCE_PROVIDER_2WAY_MSG_KEY = 'sp-two-way-messaging-key'


def store_service_status(provider_key=None, data=None):

    key = SERVICE_STATUS_KEY_PATTERN.format(provider_key=provider_key)
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    data['provider_key'] = provider_key

    if valid_heartbeat_and_datasource(data):
        redis_client.set(key, json.dumps(data))
        celery.app.send_task('rt_api.tasks.broadcast_service_status')


def valid_heartbeat_and_datasource(data):
    if data.get('heartbeat', {}).get('latest_at') and data.get('datasource', {}).get('connection_changed_at'):
        return True


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

    # Add display name from SourceProvider.
    service_status['display_name'] = display_name

    service_status.setdefault('heartbeat', {})
    service_status.setdefault('datasource', {})

    if valid_heartbeat_and_datasource(service_status):
        # Add status code based
        code, reason = calculate_status_code(service_status)
        service_status['status_code'] = code
        service_status['reason'] = reason

    # These are hacks, but should be built to identify asset type (ie. Radio
    # vs. Collar vs. Airplane)

    return service_status


ERROR_THRESHOLD_MINUTES = 10
WARNING_THRESHOLD_MINUTES = 2
ERROR_THRESHOLD = timedelta(minutes=ERROR_THRESHOLD_MINUTES)
WARNING_THRESHOLD = timedelta(minutes=WARNING_THRESHOLD_MINUTES)


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

    for minutes, delta, status_key in (
            (ERROR_THRESHOLD_MINUTES, ERROR_THRESHOLD, 'ERROR'),
        (WARNING_THRESHOLD_MINUTES, WARNING_THRESHOLD, 'WARNING')
    ):

        if heartbeat_age > delta:
            return status_key, 'Service heartbeat is older than {} minutes.'.format(minutes)

        if is_connected == False and connection_age > delta:
            return status_key, 'Data source has been disconnected for more than {} minutes.'.format(minutes)

    return 'OK', 'The service is working properly.'


def get_source_provider_statuses():

    pattern = SERVICE_STATUS_KEY_PATTERN.format(provider_key='*')
    r = redis.from_url(settings.CELERY_BROKER_URL)

    # Build a dictionary for all the services that exist in the cache.
    provider_statuses = [json.loads(r.get(k).decode('utf8'))
                         for k in r.keys(pattern)]

    provider_statuses = [_add_status_indicators(s) for s in provider_statuses]

    return provider_statuses


def is_2way_messaging_active():
    two_way_msg = cache.get(SOURCE_PROVIDER_2WAY_MSG_KEY)
    if two_way_msg is None:
        source_provider = SourceProvider.objects.annotate(two_way_message=jsonb.KeyTransform('two_way_messaging', 'additional')
                                                          ).exclude(Q(two_way_message__isnull=True) |
                                                                    Q(two_way_message=False)).exists()

        cache.set(SOURCE_PROVIDER_2WAY_MSG_KEY, source_provider, None)
        return source_provider
    return two_way_msg


def has_message_view_permission(user):
    """Does the user have at least view message permission"""
    if user.is_anonymous:
        return False
    return user.has_perm('observations.view_message') and is_2way_messaging_active()
