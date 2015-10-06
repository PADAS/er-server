"""
 Fetch and transform Savannah data into DAS input format
"""
import copy

import http.client
from functools import namedtuple
from observations.models import Observation, Source
from .plugin import DasPlugin, PluginTarget, DasPluginConfigurationError
import datetime, time
from data_input.models import PluginConf, PluginConfSource

from dateutil.parser import parse as parse_date
import pytz

import logging


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
Fix = namedtuple('Fix', ['collar_id', 'lon', 'lat', 'ts', 'speed', 'heading', 'temperature', 'height'])
field_transform = (str, float, float, __str2date, float, float, str, int)


class SavannaClient(object):

    def __init__(self, config=None):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''

        self._config = config or {}

        self.logger = logging.getLogger(self.__class__.__name__)

        if not all(x in self._config for x in ('host', 'credentials')):
            raise DasPluginConfigurationError('Not enough configuration provided to continue.')

        self.credentials = self._config.get('credentials')
        self.host = self._config.get('host')


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
        saveline = None
        if res.status == http.client.OK:
            for line in res:
                if line != saveline: # We occassionally see duplicate records in results.
                    yield self.parse_line(line.decode('utf-8').strip())
                saveline = line

    @classmethod
    def parse_line(cls, s):
        '''
        takes a record from savanna data source and creates a Fix from it, performing necessary data-type
        conversions along the way.
        :param s:
        :return:
        '''
        dt = (c(i) for c, i in zip(field_transform, s.split(',')))
        dt = Fix._make(dt)
        return dt


SOURCE_MODEL_NAME = 'SavannaTrackingRF'


def unixtimestamp(d):
    return int(time.mktime(d.timetuple()))

DEFAULT_START_TIME = datetime.datetime(2015, 8, 1, tzinfo=pytz.utc).isoformat()

class SavannaPlugin(DasPlugin):


    def __init__(self, config=None, target=None):
        super().__init__(config=config, target=target)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.client = SavannaClient(config=self.config.configuration)

    def _fetch(self):

        sources = Source.objects.filter(model_name=SOURCE_MODEL_NAME)
        for source in sources:

            try:
                pcs = PluginConfSource.objects.get(source=source, plugin_conf=self.config)
            except PluginConfSource.DoesNotExist:
                pcs = PluginConfSource(source=source, plugin_conf=self.config, additional=dict(latest_timestamp=DEFAULT_START_TIME))
                pcs.save()


            st = Observation.objects.get_max_recorded_at(source=source) or parse_date(pcs.additional['latest_timestamp'])
            lt = st
            st = unixtimestamp(st)
            st+=1

            self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)
            for observation in self.client.fetch_observations(source.manufacturer_id, start_time=st):
                lt = observation.ts
                yield (source, observation)

            pcs.additional['latest_timestamp'] = lt.isoformat()
            pcs.save()

    def _transform(self, so_tuple):
        source, observation = so_tuple
        return (source, observation._asdict())

    def execute(self):
        super().execute()


class SavannaTarget(PluginTarget):

    def _handle_item(self, item):
        (source, obs) = item
        Observation.objects.add_observation(source, obs)


