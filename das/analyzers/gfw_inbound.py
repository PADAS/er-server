import logging
from datetime import datetime

import pytz
from django.contrib.gis.geos import Point
from django.http.request import HttpRequest
from django.utils.translation import ugettext_lazy as _
from django.db.models import signals
from rest_framework import status, serializers
from rest_framework.response import Response

from accounts.models import User
from activity.models import Event
from activity.serializers import EventSerializer
from analyzers.gfw_alert_schema import ensure_gfw_event_types, GFW_EVENT_TYPES_MAP
from das_server import celery
from utils import stats
from revision.manager import RevisionMixin

logger = logging.getLogger(__name__)


class DownloadUrlsField(serializers.Serializer):
    csv = serializers.URLField()
    json = serializers.URLField()


class AlertSampleDownloaded(serializers.Serializer):
    lat = serializers.FloatField()
    long = serializers.FloatField()
    julian_day = serializers.IntegerField()
    year = serializers.IntegerField()
    confidence = serializers.IntegerField()


class AlertSample(serializers.Serializer):
    acq_date = serializers.DateField()
    acq_time = serializers.TimeField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class GFWAlertParameters(serializers.Serializer):
    layerSlug = serializers.CharField()
    alert_name = serializers.CharField()
    selected_area = serializers.CharField()
    unsubscribe_url = serializers.URLField()
    subscriptions_url = serializers.URLField()
    alert_link = serializers.URLField()
    alert_date_begin = serializers.DateField()
    alert_date_end = serializers.DateField()

    map_image = serializers.CharField(default=None)
    alerts = AlertSample(many=True)
    downloadUrls = DownloadUrlsField(default=None)


WEBHOOK_INVOCATION_COUNT_METRIC = 'gfwalerts.count'
PROCESSED_COUNT_METRIC, ERRORS_COUNT_METRIC = 'gfwalerts.processed', 'gfwalerts.errors'
PROCESSED_COUNTER, ERROR_COUNTER = 'processed', 'errors'


def process_handler_post(request):
    logger.debug('Handle GFW Alert')
    stats.increment(WEBHOOK_INVOCATION_COUNT_METRIC)

    deserialized = GFWAlertParameters(data=request.data)
    if not deserialized.is_valid():
        logger.error('Bad request received %s', deserialized.errors)
        log_metrics({PROCESSED_COUNTER: 0,
                     ERROR_COUNTER: 1})
        return Response(status=status.HTTP_400_BAD_REQUEST, data=deserialized.errors)

    logger.info(f'process_handler_alerts posted {deserialized.validated_data}', extra={
                'data': request.data})

    layer_slug = deserialized.validated_data.get('layerSlug')

    event_type_value = GFW_EVENT_TYPES_MAP.get(layer_slug)
    if event_type_value:
        logger.info('Got %s alert', layer_slug,
                    extra={'alert_type': layer_slug})
        ensure_gfw_event_types()

        event_details_dict = {
            'gfw_alert_type': layer_slug,
            'alert_link': deserialized.validated_data.get('alert_link'),
            'subscription_name': deserialized.validated_data.get('alert_name')
        }

        event_dict = {
            'event_type': event_type_value,
            'event_title': _('Global Forest Watch Alert'),
            'event_details': event_details_dict
        }

        return create_events(request, event_dict, deserialized.validated_data)

    logger.info('Ignoring %s alert', layer_slug,
                extra={'alert_type': layer_slug})
    return Response(status=status.HTTP_400_BAD_REQUEST,
                    data=dict(message=f'Unknown layerSlug: {layer_slug}'))


def create_events(request, common_fields, validated_data):

    def create_alert_event(alert_sample):
        deserialized_sample = AlertSample(data=alert_sample)
        if not deserialized_sample.is_valid():
            counts[ERROR_COUNTER] = counts[ERROR_COUNTER] + 1
            return deserialized_sample.errors()

        event_fields = {
            **common_fields,
            **{
                'location': {
                    'latitude': deserialized_sample.validated_data.get('latitude'),
                    'longitude': deserialized_sample.validated_data.get('longitude')},
                'time': datetime.combine(date=deserialized_sample.validated_data.get('acq_date'),
                                         time=deserialized_sample.validated_data.get(
                                             'acq_time'),
                                         tzinfo=pytz.UTC)
            }
        }

        return persist_event(event_fields, request, counts)

    download_urls = validated_data.get('downloadUrls')
    if download_urls:
        result = celery.app.send_task('analyzers.tasks.download_gfw_alerts', args=(download_urls.get('json'),
                                                                                   common_fields,
                                                                                   str(request.user.id)))
        logger.debug('celery submit result: %s', result)

    counts = {PROCESSED_COUNTER: 0, ERROR_COUNTER: 0}
    errors = [create_alert_event(alert)
              for alert in validated_data.get('alerts')]
    errors = filter(lambda x: len(list(x)) > 0, errors)

    log_metrics(counts)

    if len(list(errors)) > 0:
        logger.error('Bad request received %s', errors)
        return Response(status=status.HTTP_400_BAD_REQUEST, data=errors)
    else:
        return Response(status=status.HTTP_201_CREATED, data=dict(message='Alert processed'))


def process_downloaded_alerts(payload, common_event_fields, user_id):
    counts = {PROCESSED_COUNTER: 0, ERROR_COUNTER: 0}
    errors = [create_event_from_downloadedalert(alert, common_event_fields, user_id, counts)
              for alert in payload]
    errors = filter(lambda x: len(list(x)) > 0, errors)

    log_metrics(counts)

    if len(list(errors)) > 0:
        logger.warning('Errors processing downloaded alerts. %s', errors)


def create_event_from_downloadedalert(downloaded_sample, common_event_fields, user_id, counts):
    request = HttpRequest()
    request.user = User.objects.get(id=user_id)

    deserialized_sample = AlertSampleDownloaded(data=downloaded_sample)
    if not deserialized_sample.is_valid():
        counts[ERROR_COUNTER] = counts[ERROR_COUNTER] + 1
        return deserialized_sample.errors()

    julian_day = deserialized_sample.validated_data.get('julian_day')
    year = deserialized_sample.validated_data.get('year')
    confidence = deserialized_sample.validated_data.get('confidence', -1)

    event_fields = {
        **common_event_fields,
        **{
            'location': {
                'latitude': deserialized_sample.validated_data.get('lat'),
                'longitude': deserialized_sample.validated_data.get('long')},
            'time': pytz.utc.localize(datetime.strptime(f'{julian_day}{year}', '%j%Y'))
        }
    }

    event_fields.setdefault('event_details', {})['confidence'] = confidence

    return persist_event(event_fields, request, counts)


def persist_event(event_fields, request, counts):

    def pre_save_info(sender, instance, **kwargs):
        if issubclass(sender, RevisionMixin):
            setattr(instance, 'revision_user', request.user)

    # check for duplicates before serializing
    location = Point(event_fields['location']['longitude'],
                     event_fields['location']['latitude'])

    if Event.objects.filter(location=location,
                            event_time=event_fields['time'],
                            event_type__value__exact=event_fields['event_type']).exists():
        logger.warning('Event already exists - ignoring duplicate event')
    else:
        evt_serializer = EventSerializer(
            data=event_fields, context={'request': request})
        if not evt_serializer.is_valid():
            counts[ERROR_COUNTER] = counts[ERROR_COUNTER] + 1
            return evt_serializer.errors()

        signals.pre_save.connect(pre_save_info,
                                 dispatch_uid=(
                                     __name__, request, event_fields),
                                 weak=False)
        evt_serializer.create(evt_serializer.validated_data)
        counts[PROCESSED_COUNTER] = counts[PROCESSED_COUNTER] + 1
        signals.pre_save.disconnect(
            dispatch_uid=(__name__, request, event_fields))
    return {}


def log_metrics(counts):
    processed, errors = counts[PROCESSED_COUNTER], counts[ERROR_COUNTER]
    logger.debug('updating metrics. processed: %s errors: %s',
                 processed, errors)

    if errors > 0:
        stats.increment(ERRORS_COUNT_METRIC, value=errors)
    if processed > 0:
        stats.increment(PROCESSED_COUNT_METRIC, value=processed)
