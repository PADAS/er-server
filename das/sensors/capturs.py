import logging
from datetime import datetime
from typing import NamedTuple

import pytz
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from observations.models import Observation, Source
from observations.serializers import ObservationSerializer

logger = logging.getLogger(__name__)


DAS_SUBJECT_TYPE = 'vehicle'
DAS_SUBJECT_SUBTYPE = 'car'
DAS_SOURCE_TYPE = 'tracking-device'
OBS_MIN_YEAR = 2010


class CaptursDeviceObs(NamedTuple):
    """"
    Data object that represents the common fields retrieved from capturs
    payload on https://api.capturs.com/device/{device}/position
    """
    device_id: str
    name: str
    recorded_at: datetime
    lat: float
    lon: float
    additional: dict

    def is_valid(self):
        # omit old dates, and those with no pos fix
        valid_obs = (self.recorded_at.year >
                     OBS_MIN_YEAR) and self.lat and self.lon
        return valid_obs


class CaptursAdapter:
    @staticmethod
    def create_capturs_obs(data):
        """
        Validate and create capturs observation
        """
        obs = CaptursDeviceObs(
            device_id=data['device'],
            name=data['device'],
            recorded_at=CaptursAdapter.create_tz_date_from_timestamp(
                data['timestamp']),
            lat=data['latitude'],
            lon=data['longitude'],
            additional=CaptursAdapter.build_additional(data)
        )
        return obs

    @staticmethod
    def build_additional(data):
        extra = {}
        extra['altitude'] = data.get('altitude')
        extra['speed'] = data.get('speed')
        extra['move'] = data.get('move')
        return extra

    @staticmethod
    def create_tz_date_from_timestamp(timestamp):
        tz = pytz.timezone(settings.TIME_ZONE)
        localized = tz.localize(datetime.fromtimestamp(timestamp))
        utc_dt = localized.astimezone(pytz.UTC)
        return utc_dt

    @staticmethod
    def create_das_obs(capturs_obs):
        """
        Generate a DAS observation from a SpotSatellite observation
        :param capturs_obs: an SpotSatelliteObs instance
        :return: a DasObservation instance
        """
        das_obs = dict(
            location={'latitude': capturs_obs.lat,
                      'longitude': capturs_obs.lon},
            recorded_at=capturs_obs.recorded_at,
            manufacturer_id=capturs_obs.device_id,
            subject_name=capturs_obs.device_id,
            subject_type=DAS_SUBJECT_TYPE,
            subject_subtype=DAS_SUBJECT_SUBTYPE,
            model_name='capturs',
            source_type=DAS_SOURCE_TYPE,
            additional=capturs_obs.additional
        )
        return das_obs


class CaptursPushHandler:
    SENSOR_TYPE = 'capturs-tracker'

    @classmethod
    def post(cls, request, sensor_type, provider_key):
        pos_data = request.data.get('position')
        new_observations = []

        for data in pos_data:
            capturs_obs = CaptursAdapter.create_capturs_obs(data)

            # ensure source
            src = Source.objects.ensure_source(
                provider=provider_key,
                manufacturer_id=capturs_obs.device_id,
                subject={
                    'subject_subtype_id': DAS_SUBJECT_SUBTYPE,
                    'name': capturs_obs.device_id
                })

            if Observation.objects.filter(recorded_at=capturs_obs.recorded_at,
                                          source=src).exists():
                logger.info(f'Ignoring duplicate observation from {src}')
            else:
                # create observations
                observation = CaptursAdapter.create_das_obs(capturs_obs)
                observation['source'] = str(src.id)

                validator = ObservationSerializer(data=observation)
                if validator.is_valid():
                    validator.save()
                    logger.info(f'New observation created from source {src}')
                    new_observations.append(validator.data.get('id'))
                else:
                    logger.error(f'Invalid observation {observation}')
                    return Response(data=validator.errors,
                                    status=status.HTTP_400_BAD_REQUEST)

        if new_observations:
            return Response(data=new_observations, status=status.HTTP_201_CREATED)

        else:
            return Response(
                data=dict(message='Ignored duplicate observations'),
                status=status.HTTP_200_OK)
