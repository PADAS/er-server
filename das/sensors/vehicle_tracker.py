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

logger = logging.getLogger(__name__)

# map skyline vehicle types
VEHICLE_DICT = {
    'Truck': DAS_DEF_VEHICLE_TYPE,
    'Car': 'car',
    'Excavator': 'excavator',
    'Pick-Up': 'pickup',
    'Van': 'van'
}

def convert_asset_date(date_str, date_format = '%Y-%m-%d %H:%M:%S'):
    """
    Skyline AssetData format - dd/MM/yyyy HH:mm:ss
    Observation format - YYYY-MM-DDThh:mm:ss
    """
    obs_fmt = datetime.strptime(date_str, date_format)
    utc_date = pytz.utc.localize(obs_fmt)
    iso_date = utc_date.isoformat()
    return iso_date


class TractObservation(serializers.Serializer):
    GpsUTC = serializers.CharField()
    Lat = serializers.FloatField()
    Long = serializers.FloatField()
    Alt = serializers.IntegerField()
    Spd = serializers.IntegerField()
    Head = serializers.IntegerField()
    

class TractVehicleData(serializers.Serializer):
    Reg = serializers.IntegerField()
    MfgId = serializers.IntegerField()
    Records = TractObservation(many=True)

    @classmethod
    def parse_observations(cls, j_data):
        trimmed_data = {}
        # the only data we are loking for is when the Field type is 0,
        # which holds the geodata for the observation
        if 'Records' in j_data:
            obs_list = []
            for record in j_data['Records']:
                for field in record['Fields']:
                    if 'FType' in field and field['FType'] == 0:
                        obs = {}
                        obs['GpsUTC'] = field['GpsUTC']
                        obs['Lat'] = field['Lat']
                        obs['Long'] = field['Long']
                        obs['Alt'] = field['Alt']
                        obs['Spd'] = field['Spd']
                        obs['Head'] = field['Head']
                        obs_list.append(obs)
            # Note: reg and mfgid wind up being boundfields
            # after drf serialization. Not sure why
            trimmed_data['Reg'] = j_data['SerNo']
            trimmed_data['MfgId'] = j_data['IMEI']
            trimmed_data['Records'] = obs_list
        return TractVehicleData(data=trimmed_data)


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


class FollowltObservation(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    date = serializers.CharField()
    collarId = serializers.CharField()
    ttf = serializers.CharField(default=None)
    sats = serializers.CharField(default=None)
    positionId = serializers.CharField(default=None)
    serialId = serializers.CharField(default=None)
    alt = serializers.CharField(default=None)
    hdop = serializers.CharField(default=None)
    temp = serializers.CharField(default=None)
    name = serializers.CharField(default=None)


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


class TractAdapter:

    def create_das_object(self, mfg_id, subject_name, tract_record):
        das_obs = DasObservation(
            location={'latitude': tract_record['Lat'], 'longitude': tract_record['Long']},
            recorded_at=convert_asset_date(tract_record['GpsUTC']),
            manufacturer_id=mfg_id,
            subject_name=subject_name,
            subject_type=DAS_SUBJECT,
            model_name=DAS_MODEL_NAME,
            subject_subtype=DAS_DEF_VEHICLE_TYPE,
            source_type=DAS_SOURCE_TYPE,
            additional={}
        )
        logger.info("Created DAS observation %s",
                        das_obs, extra={'das.obs': das_obs})
        return das_obs


class SkylineAdapter:
    """
    Encapsulate data extraction and transform functions.
    """

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
            recorded_at=convert_asset_date(skyline_obs['GPSTime']),
            manufacturer_id=skyline_obs['Vehicle']['Id'],
            subject_name=skyline_obs['Vehicle']['Reg'],
            subject_type=DAS_SUBJECT,
            model_name=DAS_MODEL_NAME,
            subject_subtype=DAS_DEF_VEHICLE_TYPE,
            source_type=DAS_SOURCE_TYPE,
            additional={}
        )
        logger.info("Creeated DAS observation %s",
                        das_obs, extra={'das.obs': das_obs})
        return das_obs
