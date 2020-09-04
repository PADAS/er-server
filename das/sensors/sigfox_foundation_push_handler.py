import logging
import math
import os
import re
from base64 import b64encode
from datetime import datetime, timezone

import requests
from rest_framework import serializers, status
from rest_framework.response import Response

from observations.models import Observation, Source
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
    data = serializers.CharField(min_length=2, required=False)
    computedLocation = ComputedLocation(required=False)
    duplicate = serializers.NullBooleanField(required=False)
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
                parser = SigfoxPayloadParserV1 if version == 1 else SigfoxPayloadParserV2
                return cls.process_data_uplink(validated_data, provider_key, parser)
            elif validated_data.get('computedLocation'):
                return Response(data=dict(message='Message received'), status=status.HTTP_200_OK)

        logger.warn(f"SigfoxFoundationPushHandler bad request: {request.data}")
        return Response(data=sigfox_data.errors, status=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def process_data_uplink(cls, payload, provider_key, parser):
        data = payload.pop('data')
        device_id = payload.pop('deviceId')
        parsed_data = parser.parse(data, device_id)
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


class SigfoxParser:
    BYTE_PATTERN = '.{1,2}'
    byte_re = re.compile(BYTE_PATTERN)

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
    def _get_components(cls, binary_string, pattern):
        sigfox_payload_re = re.compile(pattern)
        parsed_payload = sigfox_payload_re.findall(binary_string)
        if parsed_payload:
            return parsed_payload[0]
        else:
            raise ParseException('sigfox_payload_re did not find any sigfox components in binary string')

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
    def _parse_gps_acq_time(bits):
        return int(bits, 2) * 5

    @staticmethod
    def _parse_battery_volts(bits, version=1):
        if version == 1:
            battery = int(bits, 2) * 15 / 1000
        else:  # version 2
            battery = (int(bits, 2) * 75 + 2000) / 1000
        return battery


class SigfoxPayloadParserV1(SigfoxParser):

    # look at the rhinosparser.txt linked in the JIRA ticket for a javascript example
    # https://vulcan.atlassian.net/browse/DAS-4392

    SIGFOX_PAYLOAD_PATTERN = '(.)(.{31})(.)(.{31})(.{2})(.{2})(.{4})(.{4})(.{4})(.{8})(.{8})'

    @classmethod
    def parse(cls, data, device_id):
        if len(data) != 24:
            logger.info("Invalid data, expecting only 24 bit data")
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
    def get_ubi_credentials(cls):
        username = os.getenv('UBI_API_USERNAME', 'username')
        password = os.getenv('UBI_API_PASSWORD', 'password')
        credentials = f"{username}:{password}"

        encoded_credentials = str(b64encode(credentials.encode("utf-8")), "utf-8")
        return encoded_credentials

    @classmethod
    def get_position_from_ubi(cls, data, device_id):
        ubiscale_payload = data[4:24]
        ubi_api_url = 'https://api.ubignss.com/position'
        payload = {
            "type": "ubiwifi",
            "device": device_id,
            "data": ubiscale_payload}
        credentials = cls.get_ubi_credentials()

        headers = {'Content-Type': 'application/json', 'Authorization': f'Basic {credentials}'}
        response = requests.post(url=ubi_api_url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.debug("Error when retrieving device position: ", response.text)
            return
        else:
            return response.json()

    @classmethod
    def prepare_data(cls, data):
        mode_value, mode_display, components, pattern = None, None, None, None
        try:
            bin_string = cls._to_binary_string(data)
            mode_value, mode_display = cls._parse_mode(bin_string[:3])
            if mode_value == 1:
                pattern = '(.{3})(.{5})(.)(.)(.{6})(.)(.{31})(.)(.{31})'  # gps
            elif mode_value == 2:
                pattern = '(.{3})(.{5})(.)(.)(.{6})(.{20})'  # ubiscale
            else:
                logger.debug("skipping setup, Tracking GPS and unknown modes")
            components = cls._get_components(bin_string, pattern) if pattern else None
        except Exception as exc:
            logger.exception(exc)
        return mode_value, mode_display, components

    @classmethod
    def parse(cls, data, device_id):
        result = None
        if len(data) == 2 or len(data) == 4:
            logger.info("skipping Boot/Reboot and Sigfox geolocation data")
            return

        mode_value, mode_display, components = cls.prepare_data(data)
        if not mode_value:
            logger.info("Error when preparing data, only gps and ubiscale modes allowed")
            return

        if not components:
            logger.info("Error when preparing data, Missing components in binary string ")
            return

        logger.info(f'sigfox version 2, mode: {mode_display}, parsed components: {components}')
        if mode_value == 1:
            # gps tracking -> Location provided
            result = {
                'batt_level': cls._parse_battery_volts(components[1], version=2),
                'mode': mode_display,
                'movement_it': cls._parse_movement_it(components[2]),
                'gps_state': cls._parse_state(components[3]),
                'gps_acq_time': cls._parse_gps_acq_time(components[4]),
                'latitude': cls._parse_coordinate(components[5], components[6]),
                'longitude': cls._parse_coordinate(components[7], components[8])
            }
        elif mode_value == 2:
            # ubiscale tracking -> Get location from ubi api
            device_position = cls.get_position_from_ubi(data, device_id)
            if device_position:
                result = {
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
            else:
                logger.info('No position returned from UBI')
        return result

    @staticmethod
    def _parse_movement_it(bit):
        movement_it = False if bit == 0 else True
        return movement_it


    @staticmethod
    def _parse_state(bit):
        state = 'Acquisition GPS successful' if bit == 0 else 'Acquisition GPS failed'
        return state

    @staticmethod
    def _parse_mode(bits):

        value, display = int(bits, 2), None
        if value == 1:
            display = 'Tracking GPS'
        elif value == 2:
            display = 'Tracking Ubiscale'
        return value, display


class ParseException(Exception):
    pass
