import json
import logging
from copy import deepcopy
from datetime import datetime

import pytz
import requests
from django.contrib.gis.geos import Point
from django.utils.translation import ugettext_lazy as _
from functional import seq
from rest_framework import status, serializers
from rest_framework.response import Response

from activity.models import Event
from activity.serializers import EventSerializer
from analyzers.gfw_alert_schema import ensure_gfw_event_types, GFW_EVENT_TYPES_MAP

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# All alerts include the following information:
# {
#     layerSlug: "layer slug"
#     alert_name: "subscription name",
#     selected_area: "area in meters",
#     unsubscribe_url: "url",
#     subscriptions_url: "url of the user subscriptions (../my_gfw/subscriptions)",
#     alert_link: "url of the map with the subscription",
#     alert_date_begin: "beginDate",
#     alert_date_end: "endDate"
# }
#
# VIIRS active fire alerts also include:
#
# {
#     alert_count: "number of alerts",
#     map_image: "url of the image",
#     alerts: [
#         {
#             acq_date: "date of the alert",
#             acq_time: "time of the alert",
#             latitude: "latitude in decimal degrees",
#             longitude: "longitude in decimal degrees"
#         },
#         {...}
#     ]
# }
#
# GLAD and Terra-i alerts also  include:
#
# {
#     alert_count: "number of alerts",
#     alerts: [
#         {
#             acq_date: "date of the alert",
#             acq_time: "time of the alert",
#             latitude: "latitude in decimal degrees",
#             longitude: "longitude in decimal degrees"
#         },
#         {...}
#     ],
#     downloadUrls: [
#         {
#             csv: "url",
#             json: "url"
#         }
#     ]
# }
#
# an example of json downloaded using the downloadUrls.json property from a glad alert
# {
# 	"data": [{
# 		"lat": -1.3626250000000302,
# 		"confidence": 2,
# 		"julian_day": 183,
# 		"long": 22.212625000000063,
# 		"year": 2019
# 	}, {
# 		"lat": -1.3628750000000303,
# 		"confidence": 2,
# 		"julian_day": 183,
# 		"long": 22.212625000000063,
# 		"year": 2019
# 	}, {
# 		"lat": -1.3636250000000303,
# 		"confidence": 2,
# 		"julian_day": 183,
# 		"long": 22.246625000000066,
# 		"year": 2019
# 	},]}


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


class GFWAlertHandler:
    SENSOR_TYPE = 'gfw-alert'
    PROVIDER_KEY = 'gfw'

    @classmethod
    def post(cls, request, subscription_id):
        logger.info('Handle GFW Alert', extra={'subscription_id': subscription_id})

        deserialized = GFWAlertParameters(data=request.data)
        if not deserialized.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=deserialized.errors)

        layer_slug = deserialized.validated_data.get('layerSlug')

        event_type_value = GFW_EVENT_TYPES_MAP.get(layer_slug)
        if event_type_value:
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

            return cls.create_events(request, event_dict, deserialized.validated_data)

        return Response(status=status.HTTP_400_BAD_REQUEST,
                        data=dict(message=f'Unknown layerSlug: {layer_slug}'))

    @classmethod
    def create_events(cls, request, common_fields, validated_data):

        def create_alert_event(alert_sample):
            deserialized_sample = AlertSample(data=alert_sample)
            if not deserialized_sample.is_valid():
                return deserialized_sample.errors()

            event_fields = deepcopy(common_fields)
            event_fields['location'] = {
                'latitude': deserialized_sample.validated_data.get('latitude'),
                'longitude': deserialized_sample.validated_data.get('longitude')}
            event_fields['time'] = datetime.combine(date=deserialized_sample.validated_data.get('acq_date'),
                                                    time=deserialized_sample.validated_data.get('acq_time'),
                                                    tzinfo=pytz.UTC)

            return persist_event(event_fields)

        def create_alert_from_download(downloaded_sample):
            deserialized_sample = AlertSampleDownloaded(data=downloaded_sample)
            if not deserialized_sample.is_valid():
                return deserialized_sample.errors()

            julian_day = deserialized_sample.validated_data.get('julian_day')
            year = deserialized_sample.validated_data.get('year')
            event_fields = deepcopy(common_fields)
            event_fields['location'] = {
                'latitude': deserialized_sample.validated_data.get('lat'),
                'longitude': deserialized_sample.validated_data.get('long')}
            event_fields['time'] = pytz.utc.localize(
                datetime.strptime(f'{julian_day}{year}', '%j%Y'))
            # TODO: where should the 'confidence' field be saved?

            return persist_event(event_fields)

        def persist_event(event_fields):
            # check for duplicates before serializing
            location = Point(event_fields['location']['longitude'], event_fields['location']['latitude'])

            if Event.objects.filter(location=location,
                                    event_time=event_fields['time'],
                                    event_type__value__exact=event_fields['event_type']).exists():
                logger.warning('Event already exists - ignoring duplicate event')
            else:
                evt_serializer = EventSerializer(data=event_fields, context={'request': request})
                if not evt_serializer.is_valid():
                    return evt_serializer.errors()

                evt_serializer.create(evt_serializer.validated_data)
            return {}

        errors = []
        download_urls = validated_data.get('downloadUrls')
        if download_urls is not None:
            try:
                # TODO: should this be offloaded to a separate thread
                rsp = requests.get(url=download_urls.get('json'))
                if rsp and rsp.status_code == status.HTTP_200_OK:
                    payload = json.loads(rsp.text)['data']

                    errors.extend(
                        seq(payload).
                            map(create_alert_from_download).
                            filter(lambda x: len(list(x)) > 0).
                            to_list()
                    )
            except Exception:
                logger.warning('Exception occurred while downloading alert data. Ignoring')

        errors.extend(
            seq(validated_data.get('alerts')).
                map(create_alert_event).
                filter(lambda x: len(list(x)) > 0).
                to_list()
        )

        if len(errors) > 0:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=errors)
        else:
            return Response(status=status.HTTP_201_CREATED, data=dict(message='Alert processed'))
