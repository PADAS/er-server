import logging
from datetime import datetime

import pytz

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import signals
from django.http.request import HttpRequest
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status
from rest_framework.response import Response

from accounts.models import User
from activity.models import EventDetails
from activity.serializers import EventSerializer
from analyzers.clustering_utils import cluster_alerts
from analyzers.gfw_alert_schema import (GFW_EVENT_TYPES_MAP,
                                        ensure_gfw_event_types)
from analyzers.gfw_utils import (prepare_downloadable_url,
                                 rebuild_glad_download_url,
                                 sub_id_from_unsubscribe_url)
from analyzers.models import GlobalForestWatchSubscription
from das_server import celery
from revision.manager import RevisionMixin
from utils import stats

logger = logging.getLogger(__name__)


class DownloadUrlsField(serializers.Serializer):
    csv = serializers.URLField()
    json = serializers.URLField()


class AlertSampleDownloaded(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    julian_day = serializers.IntegerField()
    year = serializers.IntegerField()
    confidence = serializers.IntegerField()
    num_clustered_alerts = serializers.IntegerField()


class FireAlertSampleDownloaded(serializers.Serializer):
    cartodb_id = serializers.IntegerField()
    the_geom = serializers.CharField()
    the_geom_webmercator = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    bright_ti4 = serializers.FloatField()
    scan = serializers.FloatField()
    track = serializers.FloatField()
    acq_date = serializers.DateTimeField()
    acq_time = serializers.CharField()
    satellite = serializers.CharField()
    confidence = serializers.CharField()
    version = serializers.CharField()
    bright_ti5 = serializers.FloatField()
    frp = serializers.FloatField()
    daynight = serializers.CharField()
    num_clustered_alerts = serializers.IntegerField()


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
    logger.info('Handle GFW Alert POST.')
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
    if not GFW_EVENT_TYPES_MAP.get(layer_slug):
        logger.info('Ignoring %s alert', layer_slug,
                    extra={'alert_type': layer_slug})
        return Response(status=status.HTTP_400_BAD_REQUEST,
                        data=dict(message=f'Unknown layerSlug: {layer_slug}'))

    ensure_gfw_event_types()

    subscription_id = sub_id_from_unsubscribe_url(
        deserialized.validated_data.get('unsubscribe_url'))

    subscriptions_qs = GlobalForestWatchSubscription.objects.filter(
        subscription_id=subscription_id)
    if subscriptions_qs.exists():
        subscription_ids = [subscription_id]
    else:
        logger.warning('Unknown subscription %s received. Processing alerts for all subscriptions in db.',
                       subscription_id)
        subscription_ids = [o.subscription_id for o in GlobalForestWatchSubscription.objects.all()
                            if layer_slug in o.additional['alert_types']]

    [process_alert_for_subscription(layer_slug, sub_id, deserialized.validated_data, str(request.user.id))
     for sub_id in subscription_ids]

    return Response(status=status.HTTP_200_OK, data=dict(message='Alerts are being processed'))


def process_alert_for_subscription(layer_slug, subscription_id, validated_data, user_id, polling=False):
    logger.info('Got %s alert', layer_slug,
                extra={'alert_type': layer_slug})
    event_type_value = GFW_EVENT_TYPES_MAP.get(layer_slug)

    event_details_dict = {
        'gfw_alert_type': layer_slug,
        'alert_link': validated_data.get('alert_link'),
        'subscription_name': validated_data.get('alert_name'),
        'subscription_id': subscription_id
    }

    event_dict = {
        'event_type': event_type_value,
        'event_title': _('Global Forest Watch Alert'),
        'event_details': event_details_dict
    }

    # todo: cleanup.
    if event_dict.get('event_type') == 'gfw_activefire_alert':
        validated_data['downloadUrls'] = prepare_downloadable_url(
            validated_data, subscription_id)

    download_urls = validated_data.get('downloadUrls')
    download_url = download_urls.get('json')
    if event_dict.get('event_type') == 'gfw_glad_alert' and not polling:
        # make sure geostore is correct in download_url
        download_url = rebuild_glad_download_url(download_url, GlobalForestWatchSubscription.objects.get(
            subscription_id=subscription_id))

    result = celery.app.send_task('analyzers.tasks.download_gfw_alerts', args=(download_url,
                                                                               event_dict,
                                                                               user_id))
    logger.info(
        'Submitted task for downloading GFW Alerts. Celery Async result: %s', result)


def process_downloaded_alerts(payload, common_event_fields, user_id):
    counts = {PROCESSED_COUNTER: 0, ERROR_COUNTER: 0}
    filtered_alerts = filter_alert_based_on_confidence(
        payload, common_event_fields)
    clustered_alerts = cluster_alerts(
        filtered_alerts, settings.GFW_CLUSTER_RADIUS, 1)
    errors = [create_event_from_downloadedalert(alert, common_event_fields, user_id, counts)
              for alert in clustered_alerts]
    errors = filter(lambda x: len(list(x)) > 0, errors)

    log_metrics(counts)

    if len(list(errors)) > 0:
        logger.warning('Errors processing downloaded alerts. %s', errors)


def create_event_from_downloadedalert(downloaded_sample, common_event_fields, user_id, counts):
    request = HttpRequest()
    request.user = User.objects.get(id=user_id)

    if common_event_fields.get('event_type') == 'gfw_activefire_alert':
        downloaded_sample['acq_date'] = parse_datetime(
            downloaded_sample['acq_date'])
        deserialized_sample = FireAlertSampleDownloaded(data=downloaded_sample)
        # logger.info("Processed deserialized sample %s", deserialized_sample)
    else:
        deserialized_sample = AlertSampleDownloaded(data=downloaded_sample)

    if not deserialized_sample.is_valid():
        counts[ERROR_COUNTER] = counts[ERROR_COUNTER] + 1
        return deserialized_sample.errors

    if common_event_fields.get('event_type') == 'gfw_activefire_alert':
        latitude = deserialized_sample.validated_data.get('latitude')
        longitude = deserialized_sample.validated_data.get('longitude')
        confidence = deserialized_sample.validated_data.get('confidence')
        time = deserialized_sample.validated_data.get('acq_date')

        bright_ti4 = deserialized_sample.validated_data.get('bright_ti4')
        bright_ti5 = deserialized_sample.validated_data.get('bright_ti5')
        scan = deserialized_sample.validated_data.get('scan')
        track = deserialized_sample.validated_data.get('track')
        frp = deserialized_sample.validated_data.get('frp')

        common_event_fields['event_details']['bright_ti4'] = bright_ti4
        common_event_fields['event_details']['bright_ti5'] = bright_ti5
        common_event_fields['event_details']['scan'] = scan
        common_event_fields['event_details']['track'] = track
        common_event_fields['event_details']['frp'] = frp

    else:
        julian_day = deserialized_sample.validated_data.get('julian_day')
        year = deserialized_sample.validated_data.get('year')
        confidence = deserialized_sample.validated_data.get('confidence', -1)
        latitude = deserialized_sample.validated_data.get('latitude')
        longitude = deserialized_sample.validated_data.get('longitude')
        time = pytz.utc.localize(
            datetime.strptime(f'{julian_day}{year}', '%j%Y'))

    num_clustered_alerts = deserialized_sample.validated_data.get(
        'num_clustered_alerts')

    common_event_fields['event_details'][
        'num_clustered_alerts'] = num_clustered_alerts

    event_fields = {
        **common_event_fields,
        **{
            'location': {
                'latitude': latitude,
                'longitude': longitude},
            'time': time,
        }
    }

    event_fields.setdefault('event_details', {})['confidence'] = confidence

    return persist_event(event_fields, request, counts)


def filter_alert_based_on_confidence(alerts, common_event_fields):
    subscription_id = common_event_fields['event_details']['subscription_id']
    gfw_query = GlobalForestWatchSubscription.objects.get(
        subscription_id=subscription_id)

    filtered_alerts = []

    for alert in alerts:
        try:
            confidence = alert['confidence']
            if common_event_fields.get('event_type') == 'gfw_activefire_alert':
                conf_confidence = gfw_query.Fire_confidence
                superset_confidence = {i.strip() for i in
                                       conf_confidence.split(',')}
            else:
                conf_confidence = gfw_query.Deforestation_confidence
                superset_confidence = {int(i) for i in
                                       conf_confidence.split(',')}

            # Checks if confidence level from glad alerts is a subset of confidence level specified in ER.
            if {confidence} <= superset_confidence:
                filtered_alerts.append(alert)
            else:
                logger.debug(
                    "GLAD Alert %s not within the confidence level" % alert)
        except KeyError:
            pass

    return filtered_alerts


def persist_event(event_fields, request, counts):
    def pre_save_info(sender, instance, **kwargs):
        if issubclass(sender, RevisionMixin):
            setattr(instance, 'revision_user', request.user)

    # check for duplicates before serializing
    location = Point(event_fields['location']['longitude'],
                     event_fields['location']['latitude'])
    confidence = event_fields['event_details']['confidence']

    qs = EventDetails.objects.filter(event__location=location,
                                     event__event_time=event_fields['time'],
                                     event__event_type__value__exact=event_fields['event_type'])
    if qs.exists():
        evt_details = qs.first()
        if event_fields['event_type'] == 'gfw_glad_alert':
            saved_conf = evt_details.data['event_details']['confidence']
            if saved_conf != confidence:
                evt_details.data['event_details']['confidence'] = confidence
                evt_details.save()
                logger.info(
                    f'event details id: {evt_details.id} GLAD confidence updated from {saved_conf} to {confidence}')
            else:
                logger.debug('Ignoring duplicate event')
        else:
            logger.debug('Ignoring duplicate event')

    else:
        evt_serializer = EventSerializer(
            data=event_fields, context={'request': request})
        if not evt_serializer.is_valid():
            counts[ERROR_COUNTER] = counts[ERROR_COUNTER] + 1
            return evt_serializer.errors

        signals.pre_save.connect(pre_save_info,
                                 dispatch_uid=(
                                     __name__, request, event_fields),
                                 weak=False)
        with transaction.atomic():
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
