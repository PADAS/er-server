import codecs
import datetime
import logging
import os
import struct
from typing import NamedTuple

import requests
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from django.conf import settings

from observations.models import Source, Observation
from observations.serializers import ObservationSerializer
from tracking.pubsub_registry import notify_new_tracks

logger = logging.getLogger(__name__)


class EarthRangerObservation(NamedTuple):
    location: dict
    recorded_at: datetime.datetime
    manufacturer_id: str
    subject_name: str
    subject_subtype: str
    additional: dict

    def build_params(self):
        return self._asdict()


class EndDevice(serializers.Serializer):
    devAddr = serializers.CharField()
    devEui = serializers.CharField(required=False, allow_null=True)
    cluster = serializers.JSONField(required=False, allow_null=True)


class GatewayInfo(serializers.Serializer):
    gwEui = serializers.CharField(required=False, allow_null=True)
    rfRegion = serializers.CharField(required=False, allow_null=True)
    rssi = serializers.IntegerField(required=False, allow_null=True)
    snr = serializers.FloatField(required=False, allow_null=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    altitude = serializers.IntegerField(required=False, allow_null=True)
    channel = serializers.IntegerField(required=False, allow_null=True)
    radioId = serializers.IntegerField(required=False, allow_null=True)
    rssis = serializers.IntegerField(required=False, allow_null=True)
    rssisd = serializers.IntegerField(required=False, allow_null=True)
    fineTimestamp = serializers.IntegerField(required=False, allow_null=True)
    antenna = serializers.IntegerField(required=False, allow_null=True)
    frequencyOffset = serializers.IntegerField(required=False, allow_null=True)


class KerlinkPushDataUp(serializers.Serializer):
    id = serializers.CharField()
    endDevice = EndDevice()
    push = serializers.BooleanField(required=False, allow_null=True)
    fPort = serializers.IntegerField(required=True, allow_null=True)
    fCntDown = serializers.IntegerField(required=True, allow_null=True)
    fCntUp = serializers.IntegerField(required=True, allow_null=True)
    confirmed = serializers.BooleanField(required=True, allow_null=True)
    payload = serializers.CharField(required=True, allow_null=True)
    encrypted = serializers.BooleanField(required=False, allow_null=True)
    ulFrequency = serializers.FloatField(required=True, allow_null=True)
    modulation = serializers.CharField(required=True, allow_null=True)
    dataRate = serializers.CharField(required=True, allow_null=True)
    recvTime = serializers.IntegerField()
    gwCnt = serializers.IntegerField(required=False, allow_null=True)
    gwInfo = GatewayInfo(many=True)
    adr = serializers.BooleanField(required=False, allow_null=True)
    codingRate = serializers.CharField(required=True, allow_null=True)
    delayed = serializers.BooleanField(required=True, allow_null=True)
    classB = serializers.BooleanField(required=False, allow_null=True)
    encodingType = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class KerlinkClient:
    headers = {
        'Content-Type': 'application/vnd.kerlink.iot-v1+json',
        'Accept': 'application/vnd.kerlink.iot-v1+json'}

    def __init__(self):
        self.username = os.getenv('KERLINK_USERNAME')
        self.password = os.getenv('KERLINK_PASSWORD')
        self.baseurl = getattr(settings, 'KERLINK_BASEURL')
        self.headers = self.headers

    def process_request(self, url_path, data=None):
        try:
            if data:
                response = requests.post(url=url_path, json=data, headers=self.headers)
            else:
                response = requests.get(url=url_path, headers=self.headers)
        except requests.exceptions.ConnectionError as cn:
            logger.exception(f"ConnectionFailure: {cn} occured for endpoint: {url_path}")
        except requests.exceptions.RequestException as exc:
            logger.exception(f"Exception raised: {exc} when processing request: {url_path}")
        else:
            return response

    def authenticate(self):
        url_path = self.baseurl + "/login"
        data = {"login": self.username, "password": self.password}
        response = self.process_request(url_path, data)

        if response:
            if response.status_code != 201:
                logger.warning(f"Fail to authentcate with status:{response.status_code} and response: {response.text}")
            else:
                return response.json()

    def get_endDevices(self, dev_eui):
        authenticate = self.authenticate()
        if authenticate:
            token = authenticate.get('token')
            self.headers['Authorization'] = f'Bearer {token}'
            url_path = self.baseurl + f'/endDevices/{dev_eui}?fields=appEui,name,profile'
            response = self.process_request(url_path)

            if response:
                if response.ok:
                    return response.json()
                logger.warning(f"Failed to process request: {url_path}. status: {response.status_code} response: {response.text}")


class KerlinkMixin:

    @staticmethod
    def format_datetime(message_time):
        timestamp = datetime.datetime.fromtimestamp(int(message_time) / 1000, datetime.timezone.utc)
        return timestamp

    @staticmethod
    def lat_lon_from_gwinfo(message):
        array = []
        location = {}
        gwInfo = message.get('gwInfo')
        for gw in gwInfo:
            lat, lon = gw.get('latitude'), gw.get('longitude')
            array.append(dict(latitude=float(lat), longitude=float(lon)) if all([lat, lon]) else location)
        return array

    @staticmethod
    def additional_info(message):
        return dict(modulation=message.get('modulation'),
                    adr=message.get('adr'),
                    dataRate=message.get('dataRate'),
                    fCntDown=message.get('fCntDown'),
                    fCntUp=message.get('fCntUp'),
                    fport=message.get('fPort'),
                    gwInfo=message.get('gwInfo'),
                    ulFrequency=message.get('ulFrequency'))

    @staticmethod
    def get_subject_subtype(end_device):
        profile = end_device.get('profile').title() if end_device else None
        if profile == 'Vehicle':
            return 'security_vehicle'
        elif profile == 'Walking':
            return 'rhino'
        elif profile == 'Static':
            return ''

    @staticmethod
    def endDevice_info(device_eui):
        kerlink = KerlinkClient()
        return kerlink.get_endDevices(device_eui)


class KerlinkHandler(KerlinkMixin):
    serializer_class = KerlinkPushDataUp
    subject_group = ['Kerlink', ]

    @classmethod
    def post(cls, request, provider_key):
        logger.info(f'Received new push message {request.data}')

        serializer = cls.serializer_class(data=request.data)
        if not serializer.is_valid():
            logger.warning(f'validation failed for received message. {serializer.errors}')
            status_msg = {"status": 400, "message": serializer.errors}
            return Response(data=status_msg, status=status.HTTP_400_BAD_REQUEST)
        else:
            return cls.process_observations(serializer.data, provider_key)

    @classmethod
    def process_observations(cls, data, provider_key):
        errors = []
        das_observation = cls.to_earthranger_observation(data)

        for o in das_observation:
            src = Source.objects.ensure_source(provider=provider_key,
                                               manufacturer_id=o.manufacturer_id,
                                               subject={
                                                   'subject_subtype_id': o.subject_subtype,
                                                   'name': o.subject_name,
                                                   'subject_groups': cls.subject_group
                                               })

            if Observation.objects.filter(source=src, recorded_at=o.recorded_at).exists():
                logger.info("Processed duplicate observation {}".format(das_observation))
            else:
                observation = {
                    'source': str(src.id),
                    'location': o.location,
                    'recorded_at': o.recorded_at,
                    'additional': o.additional
                }
                observation_serializer = ObservationSerializer(data=observation)
                if observation_serializer.is_valid():
                    observation_serializer.save()
                    logger.debug("New observation added. %s" % observation)
                    notify_new_tracks(src.id)
                else:
                    logger.warning("Error occurred while serializing observation: %s " % observation_serializer.errors)
                    errors.append(observation_serializer.errors)

        if errors:
            status_msg = {'status': 400, 'message': errors}
            return Response(data=status_msg, status=status.HTTP_400_BAD_REQUEST)
        if das_observation:
            status_ok = {'status': 201, 'message': 'Success'}
            return Response(data=status_ok, status=status.HTTP_201_CREATED)
        else:
            Response(data={}, status=status.HTTP_200_OK)

    @classmethod
    def to_earthranger_observation(cls, message):
        end_device = message.get('endDevice')
        recvtime = message.get('recvTime')
        payload = message.get('payload')
        devEui = end_device.get('devEui')
        devAddr = end_device.get('devAddr')

        device_info = cls.endDevice_info(devEui)
        subject_subtype = cls.get_subject_subtype(device_info)

        locations = cls.lat_lon_from_gwinfo(message)
        observations = []

        for location in locations:
            if all([location, recvtime, subject_subtype]):
                message_time = cls.format_datetime(recvtime)
                additional = cls.additional_info(message)
                device_name = device_info.get('name') if device_info else None

                er_observation = EarthRangerObservation(
                    location=location,
                    recorded_at=message_time,
                    manufacturer_id=devEui,
                    subject_name=device_name or devAddr or devEui,
                    subject_subtype=subject_subtype,
                    additional=additional
                )
                observations.append(er_observation)
            else:
                logger.warning(f"Received bad data for observation: {message}")
        return observations
