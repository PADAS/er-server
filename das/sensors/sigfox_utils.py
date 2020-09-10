import logging
import math
import re
from base64 import b64encode

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class SigfoxParser:
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


class SigfoxV2(SigfoxParser):
    gps_track, ubi_track = False, False

    @classmethod
    def get_ubi_credentials(cls):
        ubi_creds = settings.UBI_API_CREDENTIALS
        credentials = f"{ubi_creds.get('username')}:{ubi_creds.get('password')}"
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
            logger.debug("Error when retrieving device position: ", response.text)
            return
        else:
            return response.json()

    @classmethod
    def prepare_data(cls, data):
        mode_value, mode_display, components, pattern = None, None, None, None
        try:
            bin_string = cls._to_binary_string(data)
            mode_value, mode_display = cls.evaluate_mode(bin_string[:3])
            if cls.gps_track:
                pattern = '(.{3})(.{5})(.)(.)(.{6})(.)(.{31})(.)(.{31})'
            elif cls.ubi_track:
                pattern = '(.{3})(.{5})(.)(.)(.{6})(.{20})'
            components = cls._get_components(bin_string, pattern) if pattern else None
        except Exception as exc:
            logger.exception(exc)
        return mode_value, mode_display, components

    @classmethod
    def cache_gps_data(cls, components, device_id, seq_no, key):
        latitude = cls._parse_coordinate(components[5], components[6])
        longitude = cls._parse_coordinate(components[7], components[8])
        data = {'device_id': device_id, 'seq_no': seq_no, 'latitude': latitude, 'longitude': longitude}
        cache.set(key, data, cls.cache_timeout)

    @classmethod
    def cache_ubi_data(cls, data, device_id, seq_no, key):
        ubi_data = {'device_id': device_id, 'seq_no': seq_no, 'data': data}
        cache.set(key, ubi_data, cls.cache_timeout)

    @classmethod
    def process_gps_data(cls, device_id, seq_no, components, time, gps_key, ubi_key):
        cached_ubi = cache.get(ubi_key)
        if cached_ubi:
            data = cached_ubi.get('data')
            latitude = cls._parse_coordinate(components[5], components[6])
            longitude = cls._parse_coordinate(components[7], components[8])
            position = cls.get_position_from_ubi(device_id, data, latitude, longitude, time)
            cache.set(ubi_key, None)
            return position
        else:
            cls.cache_gps_data(components, device_id, seq_no, gps_key)

    @classmethod
    def process_ubi_data(cls, payload, device_id, seq_no, components, time, gps_key, ubi_key):
        cached_gps = cache.get(gps_key)
        data = payload.get('data')[4:24]
        if cached_gps:
            latitude = cached_gps.get('latitude')
            longitude = cached_gps.get('longitude')
            position = cls.get_position_from_ubi(device_id, data, latitude, longitude, time)
            cache.set(gps_key, None)
            return position
        else:
            cls.cache_ubi_data(data, device_id, seq_no, ubi_key)

    @classmethod
    def cache_and_process_position(cls, payload, components):
        device_id, device_position = payload.pop('deviceId'), None
        seq_no = payload.pop('seqNumber')
        time = payload.pop('time')
        gps_key = f'gps_track_record:{device_id}-{seq_no}'
        ubi_key = f'ubi_track_record:{device_id}-{seq_no}'

        if cls.gps_track:
            device_position = cls.process_gps_data(device_id, seq_no, components, time, gps_key, ubi_key)
        elif cls.ubi_track:
            device_position = cls.process_ubi_data(payload, device_id, seq_no, components, time, gps_key, ubi_key)
        if not device_position:
            logger.info('No position returned from UBI')
        return device_position


    @classmethod
    def evaluate_mode(cls, bits):
        value, display, cls.gps_track,  cls.ubi_track = int(bits, 2), None, False, False
        if value == 1:
            cls.gps_track, display = True, 'Tracking GPS'  # Tracking GPS Mode
        elif value == 2:
            cls.ubi_track, display = True, 'Tracking Ubiscale'  # Tracking Ubiscale Mode
        else:
            logger.debug("skipping setup, boot/reboot and unknown modes")
        return value, display

    @classmethod
    def get_mode_and_components(cls, payload):
        data = payload.get('data')
        if len(data) == 2 or len(data) == 4:
            logger.info("skipping Boot/Reboot and Sigfox geolocation data")
            return
        mode_value, mode_display, components = cls.prepare_data(data)
        if not mode_value:
            logger.info("Error when preparing data, only gps and ubiscale modes allowed")

        if not components:
            logger.info("Error when preparing data, Missing components in binary string ")

        logger.info(f'sigfox version 2, mode: {mode_display}, parsed components: {components}')
        return components, mode_display

    @classmethod
    def process_sigfox_tracks(cls, payload):
        components, mode_display = cls.get_mode_and_components(payload)
        device_position = cls.cache_and_process_position(payload, components)
        return components, mode_display, device_position


class ParseException(Exception):
    pass
