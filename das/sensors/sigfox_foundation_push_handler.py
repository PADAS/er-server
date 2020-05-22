import logging
import math
import re
from datetime import datetime

from rest_framework import serializers, status
from rest_framework.response import Response

from observations.models import Source, Observation
from observations.serializers import ObservationSerializer

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
    data = serializers.CharField(min_length=24, max_length=24, required=False)
    computedLocation = ComputedLocation(required=False)
    duplicate = serializers.BooleanField(required=False)
    reception = serializers.ListField(required=False)


class SigfoxFoundationPushHandler:
    SENSOR_TYPE = 'sff-tracker'
    DEFAULT_SUBJECT_SUBTYPE = 'wildlife'
    serializer_class = PayloadValidator

    @classmethod
    def post(cls, request, provider_key):
        sigfox_data = PayloadValidator(data=request.data)
        if sigfox_data.is_valid():
            validated_data = sigfox_data.validated_data
            if validated_data.get('data'):
                return cls.process_data_uplink(validated_data, cls.SENSOR_TYPE, provider_key)
            elif validated_data.get('computedLocation'):
                return Response(data=dict(message='Message received'), status=status.HTTP_200_OK)

        return Response(data=sigfox_data.errors, status=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def process_data_uplink(cls, payload, sensor_type, provider_key):
        data = payload.pop('data')
        parsed_data = SigfoxPayloadParser.parse(data)
        if parsed_data:
            device_id = payload.pop('deviceId')
            src = Source.objects.ensure_source(provider=provider_key,
                                               manufacturer_id=device_id,
                                               subject={
                                                   'subject_subtype_id': cls.DEFAULT_SUBJECT_SUBTYPE,
                                                   'name': device_id
                                               })

            recorded_at = datetime.fromtimestamp(payload.pop('time')).isoformat()
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


class SigfoxPayloadParser:

    # look at the rhinosparser.txt linked in the JIRA ticket for a javascript example
    # https://vulcan.atlassian.net/browse/DAS-4392

    BYTE_PATTERN = '.{1,2}'
    SIGFOX_PAYLOAD_PATTERN = '(.)(.{31})(.)(.{31})(.{2})(.{2})(.{4})(.{4})(.{4})(.{8})(.{8})'

    byte_re = re.compile(BYTE_PATTERN)
    sigfox_payload_re = re.compile(SIGFOX_PAYLOAD_PATTERN)

    @classmethod
    def parse(cls, data):
        try:
            bin_string = cls._to_binary_string(data)
            components = cls._get_components(bin_string)
        except Exception as ex:
            logger.exception(ex)
            return None
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

    @classmethod
    def _to_binary_string(cls, payload):
        payload_bytes = cls.byte_re.findall(payload)

        if payload_bytes:
            payload_binary_string = ''
            for each_byte in payload_bytes:
                try:
                    as_hex = int(each_byte, 16)
                except ValueError:
                    raise ParseException(f'Illegal hex value: {each_byte}')
                else:
                    # logger.debug('%x ' % as_hex)
                    as_binary = bin(as_hex).replace('0b', '')
                    while len(as_binary) < 8:
                        as_binary = '0' + as_binary

                    # logger.debug(as_binary)
                    payload_binary_string += as_binary
            # logger.debug(payload_binary_string)
            return payload_binary_string
        else:
            raise ParseException('byte_re did not find any bytes')

    @classmethod
    def _get_components(cls, binary_string):
        parsed_payload = cls.sigfox_payload_re.findall(binary_string)
        if parsed_payload:
            return parsed_payload[0]
        else:
            raise ParseException('sigfox_payload_re didnot find any sigfox components in binary string')

    @classmethod
    def _parse_coordinate(cls, sign_bit, coordinate_bits):
        multiplier = -1 if sign_bit == '1' else 1
        return multiplier * cls.get_decimal_coordinate(int(coordinate_bits, 2) / math.pow(10, 6))

    @staticmethod
    def get_decimal_coordinate(payload_component):
        degrees = math.floor(payload_component)
        minutes = payload_component % 1 / 60 * 100
        minutes = round(minutes * 1000000) / 1000000
        return degrees + minutes

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
    def _parse_gps_acq_time(bits):
        return int(bits, 2) * 5

    @staticmethod
    def _parse_speed(bits):
        return int(bits, 2) * 5

    @staticmethod
    def _parse_battery_volts(bits):
        return int(bits, 2) * 15 / 1000

    @staticmethod
    def _parse_alert(bits):
        return int(bits, 2)


class ParseException(Exception):
    pass
