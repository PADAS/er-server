import logging
from datetime import datetime

import pytz
from rest_framework import serializers, status
from rest_framework.response import Response

from observations.models import Observation, Source
from observations.serializers import ObservationSerializer

logger = logging.getLogger(__name__)


DAS_SUBJECT_TYPE = 'person'
DAS_SUBJECT_SUBTYPE = 'ranger'
DAS_SOURCE_TYPE = 'tracking-device'


class CaptursObservationSerializer(serializers.Serializer):
    device_id = serializers.CharField()
    name = serializers.CharField(default=None)
    recorded_at = serializers.DateTimeField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    additional = serializers.DictField()


class CaptursAdapter:
    @staticmethod
    def create_capturs_obs(obs_data):
        """
        Serialize and create capturs observation
        """
        obs = [
            dict(
                device_id=data.pop('device'),
                recorded_at=datetime.fromtimestamp(
                    int(data.pop('timestamp')), tz=pytz.UTC),
                lat=data.pop('latitude'),
                lon=data.pop('longitude'),
                additional=data
            ) for data in obs_data]

        return CaptursObservationSerializer(data=obs, many=True)

    @staticmethod
    def create_das_obs(capturs_obs):
        """
        Generate a DAS observation from a SpotSatellite observation
        :param capturs_obs: an SpotSatelliteObs instance
        :return: a DasObservation instance
        """
        das_obs = dict(
            location={'latitude': capturs_obs['lat'],
                      'longitude': capturs_obs['lon']},
            recorded_at=capturs_obs['recorded_at'],
            manufacturer_id=capturs_obs['device_id'],
            subject_name=capturs_obs['device_id'],
            subject_type=DAS_SUBJECT_TYPE,
            subject_subtype=DAS_SUBJECT_SUBTYPE,
            model_name='capturs',
            source_type=DAS_SOURCE_TYPE,
            additional=capturs_obs['additional']
        )
        return das_obs


class CaptursPushHandler:
    SENSOR_TYPE = 'capturs-tracker'
    serializer_class = CaptursObservationSerializer

    @classmethod
    def post(cls, request, provider_key):
        pos_data = request.data.get('position') or request.data.get('event')
        cls.observations_count = 0
        cls.provider_key = provider_key

        # serialize received data
        serializer = CaptursAdapter.create_capturs_obs(pos_data)
        if not serializer.is_valid():
            logger.error(
                f'Invalid observation records: {serializer.errors}')
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        for data in serializer.data:
            if data['lat'] == 0 and data['lon'] == 0:
                logger.info(f'skipped observation, position data not ready')
            else:
                # ensure source
                src = cls.ensure_source(data)
                cls.create_observations(src, data)

        if cls.observations_count:
            return Response(
                data={"message": f"{cls.observations_count} new observations added"},
                status=status.HTTP_201_CREATED)

        else:
            return Response(data={}, status=status.HTTP_200_OK)

    @classmethod
    def ensure_source(cls, capturs_obs):
        """ Get or create provider, source and subject """

        capturs_obs['name'] = capturs_obs['device_id']
        src = Source.objects.ensure_source(
            provider=cls.provider_key,
            manufacturer_id=capturs_obs['device_id'],
            subject={
                'subject_subtype_id': DAS_SUBJECT_SUBTYPE,
                'name': capturs_obs['device_id']
            })
        return src

    @classmethod
    def create_observations(cls, src, capturs_obs):
        """ Create an observation, unless its a duplicate """

        if Observation.objects.filter(recorded_at=capturs_obs['recorded_at'],
                                      source=src).exists():
            logger.info(f'Ignoring duplicate observation from {src}')
        else:
            observation = CaptursAdapter.create_das_obs(capturs_obs)
            observation['source'] = str(src.id)

            validator = ObservationSerializer(data=observation)

            if validator.is_valid():
                validator.save()
                logger.info(
                    f'New observation created from source {src}')
                cls.observations_count += 1
            else:
                logger.error(
                    f'Invalid observation records {validator.errors}')
