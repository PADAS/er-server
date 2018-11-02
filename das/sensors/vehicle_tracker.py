import logging
import pytz
from dateutil.parser import parse
from datetime import datetime
from typing import NamedTuple

from rest_framework import status
from rest_framework.response import Response
from rest_framework import serializers

DAS_SUBJECT = 'vehicle'
DAS_DEF_VEHICLE_TYPE = 'security_vehicle'
DAS_MODEL_NAME = 'vehicle-tracker'
DAS_SOURCE_TYPE = 'tracking-device'

# map skyline vehicle types
VEHICLE_DICT = {
    'Truck': DAS_DEF_VEHICLE_TYPE,
    'Car': 'car',
    'Excavator': 'excavator',
    'Pick-Up': 'pickup',
    'Van': 'van'
}

class SkylineVehicleData(serializers.Serializer):
    Id = serializers.IntegerField()
    Reg = serializers.CharField()
    Type = serializers.CharField()


class SkylineObservation(serializers.Serializer):
    Lat = serializers.FloatField()
    Lon = serializers.FloatField()
    GPSTime = serializers.CharField()
    Dir = serializers.CharField()
    Speed = serializers.IntegerField()
    Vehicle = SkylineVehicleData()


class SkylineObservations(serializers.Serializer):
    Messages = SkylineObservation(many=True)


class DasObservation(NamedTuple):
    """
    Data object that represents the payload that is posted to the DAS sensor API
    """
    location: dict
    recorded_at: datetime
    manufacturer_id: str
    subject_name: str
    subject_type: str
    subject_subtype: str
    model_name: str
    source_type: str
    additional: dict

    def build_params(self):
        return self._asdict()


class SkylineAdapter:
    """
    Encapsulate data extraction and transform functions.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def convert_asset_date(self, date_str):
        """
        Skyline AssetData format - dd/MM/yyyy HH:mm:ss
        Observation format - YYYY-MM-DDThh:mm:ss
        """
        obs_fmt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        utc_date = pytz.utc.localize(obs_fmt)
        iso_date = utc_date.isoformat()
        return iso_date

    def create_das_object(self, skyline_obs):
        """
        Generate a DAS observation from a SkylineObservation
        :param skyline_obs: an SkylineObservation instance
        :return: a DASObservation instance
        TODO - right now all vehicles are assigned the default type,
        security_vehicle. Make sure we have all the svg icons in place
        in the api server before using the VEHICLE_DICT
        """
        das_obs = DasObservation(
            location={'latitude': skyline_obs['Lat'], 'longitude': skyline_obs['Lon']},
            recorded_at=self.convert_asset_date(skyline_obs['GPSTime']),
            manufacturer_id=skyline_obs['Vehicle']['Id'],
            subject_name=skyline_obs['Vehicle']['Reg'],
            subject_type=DAS_SUBJECT,
            model_name=DAS_MODEL_NAME,
            subject_subtype=DAS_DEF_VEHICLE_TYPE,
            source_type=DAS_SOURCE_TYPE,
            additional={}
        )
        return das_obs
