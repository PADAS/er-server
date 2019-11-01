import logging
import math
import re
from datetime import datetime

from rest_framework import serializers

from observations.models import Source
from observations.serializers import ObservationSerializer

logger = logging.getLogger(__name__)


class MessageValidator(serializers.Serializer):
    recorded_at = serializers.DateTimeField()
    manufacturer_id = serializers.CharField()

    subject_id = serializers.CharField(default=None)


class SigfoxFoundationPushHandler:
    SENSOR_TYPE = 'sigfox-foundation-tracker'
    PROVIDER_KEY = 'sigfox-foundation'
    DEFAULT_SUBJECT_SUBTYPE = 'wildlife'

    @classmethod
    def post(cls, request, sensor_type, provider_key):
        sigfox_data = request.data
        # TODO: validate data
        if sigfox_data.get('data'):
            cls.process_data_uplink(sigfox_data, sensor_type, provider_key)
        elif sigfox_data.get('computedLocation'):
            cls.process_data_advanced(sigfox_data, sensor_type, provider_key)
        else:
            pass  # TODO: don't know how to handle this message. HTTP_400

    @classmethod
    def process_data_uplink(cls, payload, sensor_type, provider_key):
        # TODO: validate data. required params: deviceId, time, data...
        data = payload.pop('data')
        parsed_data = SigfoxPayloadParser.parse(data)

        if parsed_data:
            device_id = payload.pop('deviceId')

            src = Source.objects.ensure_source(sensor_type,
                                               provider=provider_key,
                                               manufacturer_id=device_id,
                                               subject={
                                                   'subject_subtype_id': cls.DEFAULT_SUBJECT_SUBTYPE,
                                                   'name': device_id
                                               })
            lat = parsed_data.pop('lat')
            lon = parsed_data.pop('lon')

            observation = {
                'location': {
                    'latitude': lat,
                    'longitude': lon
                },
                'recorded_at': datetime.fromtimestamp(payload.pop('time')).isoformat(),
                'source': str(src.id),
                'additional': {
                    **payload,
                    **parsed_data
                }
            }

            validator = ObservationSerializer(data=observation)
            if validator.is_valid():
                validator.save()
            else:
                logger.error('Invalid observation', observation)
                # TODO HTTP 400

        else:
            pass  # TODO couldn't parse data. HTTP_400

    @classmethod
    def process_data_advanced(cls, payload, sensor_type, provider_key):
        # TODO: validate data. required params: deviceId, time, computedLocation...
        computed_location = payload.pop('computedLocation')
        device_id = payload.pop('deviceId')

        src = Source.objects.ensure_source(sensor_type,
                                           provider=provider_key,
                                           manufacturer_id=device_id,
                                           subject={
                                               'subject_subtype_id': cls.DEFAULT_SUBJECT_SUBTYPE,
                                               'name': device_id
                                           })

        observation = {
            'location': {
                'latitude': computed_location.pop('lat'),
                'longitude': computed_location.pop('lng')
            },
            'recorded_at': datetime.fromtimestamp(payload.pop('time')).isoformat(),
            'source': str(src.id),
            'additional': {
                **payload,
                **computed_location
            }
        }

        validator = ObservationSerializer(data=observation)
        if validator.is_valid():
            validator.save()
        else:
            logger.error('Invalid observation', observation)
            # TODO HTTP 400


class ParseException(Exception):
    pass


class SigfoxPayloadParser:

    # look at the rhinosparser.txt linked in the JIRA ticket for a javascript example
    # https://vulcan.atlassian.net/browse/DAS-4392

    BYTE_PATTERN = '.{1,2}'
    # sigfox_frame_pattern = '(.{1})(.{31})(.{1})(.{31})(.{2})(.{2})(.{4})(.{4})(.{4})(.{8})(.{8})'
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
                'lat': cls._parse_coordinate(components[0], components[1]),
                'lon': cls._parse_coordinate(components[2], components[3]),
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
                    # print('%x ' % as_hex)
                    as_binary = bin(as_hex).replace('0b', '')
                    while len(as_binary) < 8:
                        as_binary = '0' + as_binary

                    # print(as_binary)
                    payload_binary_string += as_binary
            # print(payload_binary_string)
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


if __name__ == '__main__':
    sigfox_payload = '80aed31501e97f8d3470e200'
    print(SigfoxPayloadParser.parse(sigfox_payload))

