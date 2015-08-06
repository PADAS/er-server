"""
 Fetch and transform Savannah data into DAS input format
"""

import http.client
from functools import namedtuple
from observations.models import Observation, Source

from django.conf import settings

from dateutil.parser import parse as parse_date
import pytz
from redis import StrictRedis

def str2date(d):
    return parse_date(d).replace(tzinfo=pytz.utc)

Fix = namedtuple('Fix', ['collar_id', 'lon', 'lat', 'ts', 'speed', 'heading', 'temperature', 'height'])
field_transform = (str, float, float, str2date, float, float, str, int)

__redis_client = None
def redis():
    global __redis_client
    if not __redis_client:
        __redis_client = StrictRedis(**settings.CACHE_REDIS)
    return __redis_client

class SavannaException(Exception):
    pass

import copy

class SavannaClient(object):

    def __init__(self, config=None):

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

    def __init__(self, *args, **kwargs):
        pass

    def transform(self, observation):
        source = Source.objects.get(model_name=SOURCE_MODEL_NAME, manufacturer_id=observation.collar_id)
        return (source, observation._asdict())


from .plugin import DasPlugin, PluginTarget
import datetime, time
class SavannaPlugin(DasPlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self._config = kwargs.get('config', {})
        self.client = SavannaClient(self._config)
        self.transformer = SavannaTransformer(self._config)

    def generate_input(self, sources):
        pass

    def __get_start_time(self, manufacturer_id=None):
        st = self._config.get('start_time', None)

        _ = datetime.datetime(2015, 8, 1, tzinfo=pytz.utc)
        _ = int(time.mktime(_.timetuple()))
        return _


    def _fetch(self):
        sources = Source.objects.filter(model_name=SOURCE_MODEL_NAME)
        for source in sources:
            yield from self.client.fetch_observations(source.manufacturer_id, start_time=self.__get_start_time())

    def _transform(self, obj):
        return self.transformer.transform(obj)

    def execute(self):
        super().execute()


class SavannaTarget(PluginTarget):

    def _handle_item(self, item):
        (source, obs) = item
        Observation.objects.add_observation(source, obs)
        print(item)



