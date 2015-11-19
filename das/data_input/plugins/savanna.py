"""
 Fetch and transform Savannah data into DAS input format
"""
import copy

import http.client
from functools import namedtuple

from .plugin import DasPlugin, Obs, DasPluginConfigurationError
import datetime, time
from datetime import timedelta
from data_input.models import PluginConfSource


from dateutil.parser import parse as parse_date
import pytz

import logging


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
Fix = namedtuple('Fix', ['collar_id', 'longitude', 'latitude', 'recorded_at', 'speed', 'heading', 'temperature', 'height'])
field_transform = (str, float, float, __str2date, float, float, str, int)


class SavannaClient(object):

    plugin_key = 'savannah-tracking'
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


def unixtimestamp(d):
    return int(time.mktime(d.timetuple()))

DEFAULT_START_OFFSET = timedelta(days=14)

class SavannaPlugin(DasPlugin):

    plugin_key = 'savannah-tracking'

    def __init__(self, config=None, target=None):
        super().__init__(config=config, target=target)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.client = SavannaClient(config=self.config.configuration)

    def _fetch(self):

        conf_sources = PluginConfSource.objects.filter(plugin_conf=self.config)
        for conf_source in conf_sources:

            try:
                st = parse_date(conf_source.additional['latest_timestamp'])
            except Exception as e:
                st = datetime.datetime.utcnow() - DEFAULT_START_OFFSET

            try:
                lt = st
                st = unixtimestamp(st)
                st+=1

                source = conf_source.source
                self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)
                for fix in self.client.fetch_observations(source.manufacturer_id, start_time=st):
                    lt = fix.recorded_at
                    yield (source, fix)

                conf_source.additional['latest_timestamp'] = lt.isoformat()
                conf_source.save()
            except Exception as e:
                self.logger.exception("Error fetching savanna collar data")

    def _transform(self, item):
        source, o = item

        side_data = dict((k, o.__getattribute__(k)) for k in ('speed', 'heading', 'temperature', 'height'))
        return Obs(source=source, recorded_at=o.recorded_at, latitude=o.latitude, longitude=o.longitude,
                   additional=side_data)

    def execute(self):
        super().execute()




