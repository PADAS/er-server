"""
 Fetch and transform Savannah data into DAS input format
"""

import http.client
from functools import namedtuple
from observations.models import Observation, Source
from django.contrib.gis.geos import Point

from dateutil.parser import parse as parse_date
import pytz

from dateutil.parser import parse as parse_date
from datetime import tzinfo
import pytz

Fix = namedtuple('Fix', ['collar_id', 'lon', 'lat', 'ts', 'speed', 'heading', 'temperature', 'height'])

class SavannaException(Exception):
    pass

import copy

class SavannaClient(object):

    def __init__(self):

        # TODO: Move this to provider_settings.
        self.credentials = {
            'uid': 'ste', 'pwd': 'ndovu4'
        }
        self.host = "41.207.72.20"

    def fetch_observations(self, collar_id, start_time, end_time=None):
        '''
        Fetch observations from Savannah data-source for a particular collar.
        :param collar_id: collar_id from trackingmaster record.
        :param start_time: unix timestamp for earliest data to fetch.
        :param end_time: <not used>
        :return: generator, yielding individual records.
        '''

        conn = http.client.HTTPConnection(self.host)

        payload = copy.copy(self.credentials)
        payload.update(dict(unixtime=str(start_time), collar=collar_id))

        payload = ['='.join((k, v)) for k, v in payload.items()]
        payload = '&'.join(payload)

        headers = { 'accept': "*/*",
                    'content-type': 'application/x-www-form-urlencoded'
                    }

        conn.request("POST", "/savannah/get_data.asp", payload, headers)

        res = conn.getresponse()
        if res.status == http.client.OK:
            for line in res:
                yield self.parse_line(line.decode('utf-8').strip())

    @classmethod
    def parse_line(cls, s):
        dt = Fix._make(s.split(','))
        dt = dt._replace(ts=parse_date(dt.ts).replace(tzinfo=pytz.utc))
        return dt

    @classmethod
    def test_fix(cls, sample):
        return cls.parse_line(sample)


SOURCE_MODEL_NAME = 'SavannaTrackingRF'

class SavannaTransformer(object):

    def __init__(self):
        pass

    def transform(self, observation):
        source = Source.objects.get(model_name=SOURCE_MODEL_NAME, manufacturer_id=observation.collar_id)
        obs = observation._asdict()
        loc = Point(float(obs.pop('lat')), float(obs.pop('lon')))
        ts = obs.pop('ts')


        # TODO: move this save outside of transformer.
        obs = Observation(source=source, location=loc, recorded_at=ts, additional=obs)
        obs.save()
        return observation
