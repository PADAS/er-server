import logging
from datetime import datetime, timezone

from rest_framework import serializers, status
from rest_framework.response import Response

from observations.models import Observation, Source
from observations.serializers import ObservationSerializer

from .sigfox_utils import SigfoxParser, SigfoxV2

logger = logging.getLogger(__name__)


class ComputedLocation(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    radius = serializers.IntegerField(required=False)
    source = serializers.IntegerField(required=False)
    status = serializers.IntegerField(required=False)


class PayloadValidator(serializers.Serializer):
    deviceId = serializers.CharField()
    time = serializers.IntegerField()
    seqNumber = serializers.IntegerField()
    data = serializers.CharField(min_length=2, required=False)
    computedLocation = ComputedLocation(required=False)
    duplicate = serializers.BooleanField(required=False)
    reception = serializers.ListField(required=False)


class SigfoxFoundationPushHandler:
    SENSOR_TYPE = 'sff-tracker'
    SENSOR_TYPE_V2 = 'sff-tracker-v2'
    DEFAULT_SUBJECT_SUBTYPE = 'wildlife'
    serializer_class = PayloadValidator

    @classmethod
    def post(cls, request, provider_key, version):
        sigfox_data = PayloadValidator(data=request.data)
        if sigfox_data.is_valid():
            validated_data = sigfox_data.validated_data
            if validated_data.get('data'):
                return cls.process_data_uplink(validated_data, provider_key, version)
            elif validated_data.get('computedLocation'):
                return Response(data=dict(message='Message received'), status=status.HTTP_200_OK)
        return Response(data=sigfox_data.errors, status=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def process_data_uplink(cls, payload, provider_key, version):
        device_id = payload.get('deviceId')
        if version == 1:
            parsed_data = SigfoxPayloadParserV1.parse(payload)
        else:
            components, mode_display, device_position = SigfoxV2.process_sigfox_tracks(payload)
            parsed_data = SigfoxPayloadParserV2.parse(components, mode_display, device_position)
        if parsed_data:
            src = Source.objects.ensure_source(provider=provider_key,
                                               manufacturer_id=device_id,
                                               subject={
                                                   'subject_subtype_id': cls.DEFAULT_SUBJECT_SUBTYPE,
                                                   'name': device_id
                                               })

            recorded_at = datetime.fromtimestamp(payload.pop('time'), timezone.utc).isoformat()
            # for data_uplink this test is sufficient for dups...
            if Observation.objects.filter(source=src, recorded_at=recorded_at).exists():
                logger.info('Ignoring duplicate observation from %s', src)
                return Response(data=dict(message='Ignored duplicate message'), status=status.HTTP_200_OK)

            lat = parsed_data.pop('latitude')
            lon = parsed_data.pop('longitude')

            observation = {
                'location': {
                    'latitude': lat,
                    'longitude': lon
                },
                'recorded_at': recorded_at,
                'source': str(src.id),
                'additional': {
                    **payload,
                    **parsed_data
                }
            }
            logger.debug('data_uplink', observation)

            validator = ObservationSerializer(data=observation)
            if validator.is_valid():
                validator.save()
                return Response(data=validator.data.get('id'), status=status.HTTP_201_CREATED)
            else:
                logger.error('Invalid observation %s', observation)
                return Response(data=validator.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(data=dict(message='Unable to parse data'), status=status.HTTP_400_BAD_REQUEST)


class SigfoxPayloadParserV1(SigfoxParser):

    # look at the rhinosparser.txt linked in the JIRA ticket for a javascript example
    # https://vulcan.atlassian.net/browse/DAS-4392

    SIGFOX_PAYLOAD_PATTERN = '(.)(.{31})(.)(.{31})(.{2})(.{2})(.{4})(.{4})(.{4})(.{8})(.{8})'

    @classmethod
    def parse(cls, payload):
        data = payload.pop('data')
        if len(data) != 24:
            logger.info("Invalid payload, processing enabled for only 24 bit data")
            return
        try:
            bin_string = cls._to_binary_string(data)
            components = cls._get_components(bin_string, cls.SIGFOX_PAYLOAD_PATTERN)
        except Exception as ex:
            logger.exception(ex)
            return
        else:
            logger.debug('parsed components', components)
            return {
                'latitude': cls._parse_coordinate(components[0], components[1]),
                'longitude': cls._parse_coordinate(components[2], components[3]),
                'hdop': cls._parse_hdop(components[4]),
                'sat': cls._parse_sat(components[5]),
                'unknown_field': int(components[6], 2),
                'gps_acq_time': cls._parse_gps_acq_time(components[7]),
                'speed': cls._parse_speed(components[8]),
                'batt_level': cls._parse_battery_volts(components[9]),
                'alert': cls._parse_alert(components[10]),
            }


    @staticmethod
    def _parse_hdop(bits):
        hdop = -1
        parsed_hdop = int(bits, 2)
        if parsed_hdop == 3:
            hdop = 600
        elif parsed_hdop == 2:
            hdop = 200
        elif parsed_hdop == 1:
            hdop = 100
        elif parsed_hdop == 0:
            hdop = 0

        return hdop

    @staticmethod
    def _parse_sat(bits):
        return int(bits, 2) * 2 + 2

    @staticmethod
    def _parse_speed(bits):
        return int(bits, 2) * 5

    @staticmethod
    def _parse_alert(bits):
        return int(bits, 2)

class SigfoxPayloadParserV2(SigfoxParser):
    # Decoding described in parserTektos.docx attached in the below ticket
    # https://vulcan.atlassian.net/browse/DAS-5294

    @classmethod
    def parse(cls, components, mode_display, device_position):
        if components and device_position:
            return {
                'batt_level': cls._parse_battery_volts(components[1], version=2),
                'mode': mode_display,
                'movement_it': cls._parse_movement_it(components[2]),
                'gps_state': cls._parse_state(components[3]),
                'gps_acq_time': cls._parse_gps_acq_time(components[4]),
                'latitude': device_position.get('lat'),
                'longitude': device_position.get('lng'),
                'altitude': device_position.get('alt'),
                'accuracy': device_position.get('accuracy')
            }

    @staticmethod
    def _parse_movement_it(bit):
        movement_it = False if bit == 0 else True
        return movement_it

    @staticmethod
    def _parse_state(bit):
        state = 'Acquisition GPS successful' if bit == 0 else 'Acquisition GPS failed'
        return state
