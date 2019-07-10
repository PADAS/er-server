import uuid
import logging

from rest_framework import status, serializers
from rest_framework.response import Response

from analyzers.models.gfw import GlobalForestWatchSubscription
from analyzers.gfw_alert_schema import ensure_gfw_event_type
from activity.serializers import EventSerializer

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


class AlertSample(serializers.Serializer):
    acq_date = serializers.DateField()
    acq_time = serializers.TimeField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class GFWAlertParameters(serializers.Serializer):
    layerSlug = serializers.CharField()
    alert_name = serializers.CharField()
    selected_area = serializers.CharField()
    unsubscribe_url = serializers.CharField()
    subscriptions_url = serializers.CharField()
    alert_link = serializers.CharField()
    alert_date_begin = serializers.DateField()
    alert_date_end = serializers.DateField()

    map_image = serializers.CharField(default=None)
    alerts = AlertSample(many=True)


class GFWAlertHandler:
    SENSOR_TYPE = 'gfw-alert'

    @classmethod
    def post(cls, request, subscription_id):
        logger.info(f'GFW-ALERT for {subscription_id}')
        # this sub_id exisits in db: 10fa8e36718644fd8dd8ef7d101b1e28

        try:
            subscription_uuid = uuid.UUID(hex=subscription_id)
        except ValueError:
            logger.exception(f'{subscription_id} is not formatted as a UUID')
            return Response(data={'message': f'Subscription id {subscription_id} is not formatted correctly'},
                            status= status.HTTP_400_BAD_REQUEST)

        deserialized = GFWAlertParameters(data=request.data)
        if not deserialized.is_valid():
            return Response(data=deserialized.errors,
                            status=status.HTTP_400_BAD_REQUEST)

        # write to db if we can lookup subscription_id in the model. else not found...
        if GlobalForestWatchSubscription.objects.get(pk=subscription_uuid) is not None:
            layer_slug = deserialized.validated_data.get('layerSlug')
            if layer_slug in ['viirs-active-fires', 'glad-alerts', 'terrai-alerts']:
                event_dict = dict(event_type='gfw_alert',
                                  event_title='Global Forest Watch Alert')

                ensure_gfw_event_type()

                # location = {'latitude': deserialized.validated_data.get((''))}
                event_dict['gfw_alert_type'] = layer_slug
                event_dict['alert_url'] = deserialized.validated_data.get('alert_link')
                event_dict['subscription_name'] = deserialized.validated_data.get('alert_name')
                event_dict['selected_area'] = deserialized.validated_data.get('selected_area')
                event_dict['subscriptions_url'] = deserialized.validated_data.get('subscriptions_url')
                event_dict['unsubscribe_url'] = deserialized.validated_data.get('unsubscribe_url')

                return cls.create_events(request, event_dict, deserialized.validated_data)

        else:
            return Response(data={'message': f'Subscription id {subscription_id} not found'},
                            status=status.HTTP_404_NOT_FOUND)

    @classmethod
    def create_events(cls, request, event_dict, validated_data):
        alerts = validated_data.get('alerts')

        evt_serializer = EventSerializer(data=event_dict, context={'request': request})
        if not evt_serializer.is_valid():
            return Response(data=evt_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        event = evt_serializer.create(evt_serializer.validated_data)
        return Response(data={'message': f'Alert processed, id: {event.id}'},
                        status=status.HTTP_201_CREATED)