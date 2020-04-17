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
    def create_capturs_obs(data):
        """
        Serialize and create capturs observation
        """
        obs = CaptursObservationSerializer(data=dict(
            device_id=data.pop('device'),
            recorded_at=datetime.fromtimestamp(
                int(data.pop('timestamp')), tz=pytz.UTC),
            lat=data.pop('latitude'),
            lon=data.pop('longitude'),
            additional=data
        ))
        return obs

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

    @classmethod
    def post(cls, request, sensor_type, provider_key):
        pos_data = request.data.get('position') or request.data.get('event')
        observations_count = 0

        for data in pos_data:
            if data['latitude'] == 0 and data['longitude'] == 0:
                logger.info(f'skipped observation, position data not ready')
            else:
                serializer = CaptursAdapter.create_capturs_obs(data)
                if not serializer.is_valid():
                    logger.error(
                        f'Invalid observation records {serializer.errors}')
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

                capturs_obs = serializer.data
                capturs_obs['name'] = capturs_obs['device_id']

                # ensure source
                src = Source.objects.ensure_source(
                    provider=provider_key,
                    manufacturer_id=capturs_obs['device_id'],
                    subject={
                        'subject_subtype_id': DAS_SUBJECT_SUBTYPE,
                        'name': capturs_obs['device_id']
                    })

                if Observation.objects.filter(recorded_at=capturs_obs['recorded_at'],
                                              source=src).exists():
                    logger.info(f'Ignoring duplicate observation from {src}')
                else:
                    # create observations
                    observation = CaptursAdapter.create_das_obs(capturs_obs)
                    observation['source'] = str(src.id)

                    validator = ObservationSerializer(data=observation)

                    if validator.is_valid():
                        validator.save()
                        logger.info(
                            f'New observation created from source {src}')
                        observations_count += 1
                    else:
                        logger.error(
                            f'Invalid observation records {validator.errors}')
                        return Response(data=validator.errors,
                                        status=status.HTTP_400_BAD_REQUEST)

        if observations_count > 0:
            return Response(
                data={"message": f"{observations_count} new observations added"},
                status=status.HTTP_201_CREATED)

        else:
            return Response(data={}, status=status.HTTP_200_OK)
