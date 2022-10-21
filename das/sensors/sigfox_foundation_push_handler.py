import logging
import math
import re
from base64 import b64encode
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.cache import cache
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
    deviceId = serializers.CharField(required=True)
    time = serializers.IntegerField()
    seqNumber = serializers.IntegerField()
    data = serializers.CharField(min_length=2, required=False)
    computedLocation = ComputedLocation(required=False)
    duplicate = serializers.NullBooleanField(required=False)
    reception = serializers.ListField(required=False)


class SigfoxFoundationPushHandler:
    serializer_class = PayloadValidator
    DEFAULT_SUBJECT_SUBTYPE = 'wildlife'

    BYTE_PATTERN = '.{1,2}'
    byte_re = re.compile(BYTE_PATTERN)
    cache_timeout = 300  # 5 minutes

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
    def process_parsed_data(cls, payload, provider_key, parsed_data):
        device_id = payload.pop('deviceId')
        if parsed_data:
            src = Source.objects.ensure_source(provider=provider_key,
                                               manufacturer_id=device_id,
                                               subject={
                                                   'subject_subtype_id': cls.DEFAULT_SUBJECT_SUBTYPE,
                                                   'name': device_id
                                               })

            recorded_at = datetime.fromtimestamp(int(payload.pop('time')), timezone.utc).isoformat()
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
                err_message = validator.errors
        else:
            err_message = dict(message='Unable to parse data')
        return Response(data=err_message, status=status.HTTP_400_BAD_REQUEST)


    @classmethod
    def _get_components(cls, binary_string, sigfox_payload_re):
        parsed_payload = sigfox_payload_re.findall(binary_string)
        if parsed_payload:
            return parsed_payload[0]
        else:
            raise ParseException('sigfox_payload_re did not find any sigfox components in binary string')


class SigfoxV1Handler(SigfoxFoundationPushHandler):
    SENSOR_TYPE = 'sff-tracker'
    V1_UPLINK_PAYLOAD_LENGTH = 24
    SIGFOX_PAYLOAD_PATTERN = '(.)(.{31})(.)(.{31})(.{2})(.{2})(.{4})(.{4})(.{4})(.{8})(.{8})'
    sigfox_payload_re = re.compile(SIGFOX_PAYLOAD_PATTERN)

    @classmethod
    def post(cls, request, provider_key):
        sigfox_data = PayloadValidator(data=request.data)
        if sigfox_data.is_valid():
            validated_data = sigfox_data.validated_data
            data = validated_data.get('data')
            if data and len(data) == cls.V1_UPLINK_PAYLOAD_LENGTH:
                components = cls.process_sigfoxv1_data(validated_data)
                parsed_data = SigfoxPayloadParserV1.parse(components)
                return cls.process_parsed_data(request.data, provider_key, parsed_data)
            else:
                logger.warning(f'SigfoxV1Handler ignoring request: {request.data}')
                return Response(data=dict(message='Message received'), status=status.HTTP_200_OK)
        else:
            logger.warning(f"SigfoxV1Handler bad request: {request.data}")
            return Response(data=sigfox_data.errors, status=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def process_sigfoxv1_data(cls, validated_data):
        try:
            bin_string = cls._to_binary_string(validated_data.get('data'))
            components = cls._get_components(bin_string, cls.sigfox_payload_re)
            return components
        except Exception as ex:
            logger.exception(ex)


class SigfoxV2Handler(SigfoxFoundationPushHandler):
    SENSOR_TYPE = 'sff-tracker-v2'
    GPS_TRACK, UBI_TRACK = 1, 2
    V2_UPLINK_PAYLOAD_LENGTH = 22

    GPS_PATTERN = '(.{3})(.{5})(.)(.)(.{6})(.)(.{31})(.)(.{31})'
    UBI_PATTERN = '(.{3})(.{5})(.)(.)(.{6})(.{20})'

    gps_payload_re = re.compile(GPS_PATTERN)
    ubi_payload_re = re.compile(UBI_PATTERN)

    @classmethod
    def post(cls, request, provider_key):
        sigfox_data = PayloadValidator(data=request.data)
        if sigfox_data.is_valid():
            validated_data = sigfox_data.validated_data
            uplink_data = validated_data.get('data')
            computed_location = validated_data.pop('computedLocation', None)

            if uplink_data and len(uplink_data) >= cls.V2_UPLINK_PAYLOAD_LENGTH:
                return cls.decode_and_process_uplink_data(validated_data, provider_key)
            elif computed_location:
                return cls.process_computed_location(validated_data, computed_location, provider_key)
            else:
                message = f"Ignoring Boot/reboot, geolocation, and unknown record types. Data: {uplink_data}"
                logger.info(message)
                return Response(data=dict(message=message), status=status.HTTP_200_OK)

        logger.warning(f"SigfoxV2Handler bad request: {request.data}")
        return Response(data=sigfox_data.errors, status=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def decode_and_process_uplink_data(cls, payload, provider_key):
        data = payload.pop('data')
        seq_no = payload.pop('seqNumber')
        device_id = payload.get('deviceId')
        time = payload.get('time')
        key = f'{device_id}-{seq_no}'
        components, mode, mode_display = cls.get_mode_and_components(data)

        if mode == cls.GPS_TRACK:
            return cls.process_gps_data(device_id, payload, provider_key, components, mode_display)
        elif mode == cls.UBI_TRACK:
            cls.cache_ubi_data(device_id, seq_no, key, data, time, components, mode_display)
            message = f'Uplink ubi payload, successfully cached for device: {device_id}'
        else:
            message = f'Ignoring setup and unknown track modes, data: {payload}'
        return Response(data=dict(message=message), status=status.HTTP_200_OK)

    @classmethod
    def process_gps_data(cls, device_id, payload, provider_key, components, mode_display):
        position = {
            'latitude': SigfoxParser._parse_coordinate(components[5], components[6]),
            'longitude': SigfoxParser._parse_coordinate(components[7], components[8])
        }
        if position:
            parsed_data = SigfoxPayloadParserV2.parse(position, components, mode_display)
            return cls.process_parsed_data(payload, provider_key, parsed_data)
        else:
            message = f"No valid gps position for device: {device_id}"
            return Response(data=dict(message=message), status=status.HTTP_200_OK)


    @classmethod
    def cache_ubi_data(cls, device_id, seq_no, key, data, time, components, mode):
        data = data[4:24]
        ubi_data = {'mode': mode, 'device_id': device_id, 'seq_no': seq_no, 'time': time, 'components': components, 'ubiscale_data': data}
        cache.set(key, ubi_data, cls.cache_timeout)


    @classmethod
    def process_computed_location(cls, validated_data, computed_location, provider_key):
        device_id = validated_data.get("deviceId")
        seq_no = validated_data.pop('seqNumber')

        uplink_key = f'{device_id}-{seq_no}'
        cached_uplink_data = cache.get(uplink_key)
        if cached_uplink_data:
            components = cached_uplink_data.get('components')
            mode = cached_uplink_data.get('mode')
            position = cls.process_ubi_position(computed_location, cached_uplink_data, device_id)
            cache.set(uplink_key, None)
            if position:
                parsed_data = SigfoxPayloadParserV2.parse(position, components, mode)
                if parsed_data:
                    return cls.process_parsed_data(validated_data, provider_key, parsed_data)
            else:
                message = 'No position returned from Ubi'
                return Response(data=dict(message=message), status=status.HTTP_200_OK)

        else:
            return Response(data={}, status=status.HTTP_200_OK)


    @classmethod
    def process_ubi_position(cls, computed_location, cached, device_id):
        data = cached.get('ubiscale_data')
        lat = computed_location.get('lat')
        lng = computed_location.get('lng')
        time = cached.get('time')

        ubi_position = cls.get_position_from_ubi(device_id, data, lat, lng, time)
        if ubi_position:
            position = {
                'latitude': ubi_position.get('lat'),
                'longitude': ubi_position.get('lng'),
                'altitude': ubi_position.get('alt'),
                'accuracy': ubi_position.get('accuracy')
                   }
            return position


    @classmethod
    def get_ubi_credentials(cls):
        credentials = f"{settings.UBI_API_USERNAME}:{settings.UBI_API_PASSWORD}"
        encoded_credentials = str(b64encode(credentials.encode("utf-8")), "utf-8")
        return encoded_credentials

    @classmethod
    def get_position_from_ubi(cls, device_id, data, latitude, longitude, time):
        ubi_api_url = settings.UBI_API_URL
        ubiscale_payload = {
            "network": "sigfox",
            "device": device_id,
            "data": data,
            "time": time,
            "lat": latitude,
            "lng": longitude
        }
        credentials = cls.get_ubi_credentials()
        headers = {'Content-Type': 'application/json', 'Authorization': f'Basic {credentials}'}
        try:
            response = requests.post(url=ubi_api_url, headers=headers, json=ubiscale_payload)
        except requests.exceptions.RequestException as e:
            logger.exception(e)
            return

        if response.status_code != 200:
            logger.warning("Error when retrieving device position: %s", response.text)
            return
        else:
            return response.json()

    @classmethod
    def prepare_data(cls, data):
        mode, mode_display, components, payload_re = None, None, None, None
        try:
            bin_string = cls._to_binary_string(data)
            mode, mode_display = cls.evaluate_mode(bin_string[:3])
            if mode == cls.GPS_TRACK:
                payload_re = cls.gps_payload_re
            elif mode == cls.UBI_TRACK:
                payload_re = cls.ubi_payload_re
            components = cls._get_components(bin_string, payload_re) if payload_re else None
        except Exception as exc:
            logger.exception(exc)

        return mode, mode_display, components

    @classmethod
    def evaluate_mode(cls, bits):
        value, display, invalid_mode = int(bits, 2), None, None
        if value == 0:
            invalid_mode = 'Setup'
        elif value == cls.GPS_TRACK:
            display = 'Tracking GPS'
        elif value == cls.UBI_TRACK:
            display = 'Tracking Ubiscale'
        else:
            invalid_mode = 'Unknown'
        if invalid_mode or not display:
            logger.warning(f"Invalid data mode: {invalid_mode}. Only GPS and Ubiscale modes allowed.")
        return value, display

    @classmethod
    def get_mode_and_components(cls, data):
        mode_value, mode_display, components = cls.prepare_data(data)
        logger.info(f'sigfox version 2, mode: {mode_display}, parsed components: {components}')
        return components, mode_value, mode_display


class SigfoxParser:
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
    @classmethod
    def parse(cls, components):
        if components:
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
    def parse(cls, position, components, mode):
        if components:
            return {
                'batt_level': cls._parse_battery_volts(components[1], version=2),
                'mode': mode,
                'movement_it': cls._parse_movement_it(components[2]),
                'gps_state': cls._parse_state(components[3]),
                'gps_acq_time': cls._parse_gps_acq_time(components[4]),
                **position
            }


    @staticmethod
    def _parse_movement_it(bit):
        movement_it = False if bit == 0 else True
        return movement_it

    @staticmethod
    def _parse_state(bit):
        state = 'Acquisition GPS successful' if bit == 0 else 'Acquisition GPS failed'
        return state


class ParseException(Exception):
    pass
