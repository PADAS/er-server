"""
 Fetch and transform Savannah data into DAS input format
"""
from functools import namedtuple

from .plugin import DasPlugin, Obs, DasPluginConfigurationError
import datetime, time
from datetime import timedelta
from data_input.models import PluginConfSource
import requests


from dateutil.parser import parse as parse_date
import pytz

import logging


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)

def __awtCoord2Coord(val):
    val = float(val)
    return val/60.0

# Helpers for parsing lines from AWT datasource. The key is the collar_id prefix for which each ntuple and
# transforms list should be applied.
parser_transforms = {
    'AM': { # Version 2
        'ntuple': namedtuple('AWTGSM2Fix', ['collar_id', 'n0', 'longitude', 'latitude', 'recorded_at', 'speed',
                                            'heading', 'temperature', 'height']),
        'transforms': (str, str, __awtCoord2Coord, __awtCoord2Coord,  __str2date, float, float, float, int)
    },

    'AG':{ # Version 3
        'ntuple': namedtuple('AWTGSM3Fix', ['collar_id', 'sequence', 'longitude', 'latitude', 'recorded_at', 'speed',
                                            'heading', 'temperature', 'n0', 'height', 'dop', 'n1']),
        'transforms': (str, int, __awtCoord2Coord, __awtCoord2Coord,  __str2date, float, float, float, str, float,
                       int, str)
    },
}


class AWTHttpClient(object):

    def __init__(self, config=None):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''

        self._config = config or {}

        self.logger = logging.getLogger(self.__class__.__name__)

        if not all(x in self._config for x in ('api_url',)):
            raise DasPluginConfigurationError('Not enough configuration provided to continue.')

        # self.credentials = self._config.get('credentials')
        self.api_url = self._config.get('api_url')


    def fetch_observations(self, collar_id, start_time, end_time=None):
        '''
        Fetch observations from Savannah data-source for a particular collar.
        :param collar_id: collar_id from trackingmaster record.
        :param start_time: unix timestamp for earliest data to fetch.
        :param end_time: <not used>
        :return: generator, yielding individual records.
        '''

        parser_f = self.line_parser(collar_id)

        end_time = end_time or datetime.datetime.utcnow()

        params = {'UID': collar_id,
                   'Start': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                   'Stop': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                   }

        headers = {
            'accept': "*/*"
        }

        r = requests.get(self.api_url, params=params, headers=headers)

        saveline = None
        if r.status_code == requests.codes.ok:

            for line in r.text.split('\r'):
                if len(line.strip()) < 1:
                    continue

                if line != saveline: # We occassionally see duplicate records in results.
                    _ = parser_f(line.strip())
                    if _:
                        yield _
                saveline = line

    @classmethod
    def line_parser(cls, collar_id):

        '''
        :param collar_id: the parser logic is deterimed by the prefix of the collar_id.
        :return:
        '''
        parser_config = parser_transforms.get(collar_id[:2])

        if not parser_config:
            expected_prefixes = ','.join(parser_transforms.keys())
            raise ValueError('Collar_id %s has a prefix that I don\'t know about. I expect one of %s '
                             % (collar_id, expected_prefixes))

        def f(line):
            '''
            takes a record from AWT http data source and creates a Fix from it, performing necessary data-type
            conversions along the way.
            :param s:
            :return:
            '''
            try:
                dt = (c(i) for c, i in zip(parser_config['transforms'], line.split('\t')))
                dt = parser_config['ntuple']._make(dt)
                return dt
            except Exception as e:
                pass
        return f


DEFAULT_START_OFFSET = timedelta(days=7)

class AWTHttpPlugin(DasPlugin):

    plugin_key = 'awt-http'

    def initConfig(self):
        self.client = AWTHttpClient(config=self.config.configuration)

    def _fetch(self):

        conf_sources = PluginConfSource.objects.filter(plugin_conf=self.config)
        for conf_source in conf_sources:

            try:
                st = parse_date(conf_source.additional['latest_timestamp'])
            except Exception as e:
                st = datetime.datetime.utcnow() - DEFAULT_START_OFFSET

            lt = st
            st = st + timedelta(seconds=1)
            try:
                source = conf_source.source
                notify = False
                self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)
                for fix in self.client.fetch_observations(source.manufacturer_id, start_time=st):
                    lt = fix.recorded_at
                    yield (source, fix)
                    notify = True


                conf_source.additional['latest_timestamp'] = lt.isoformat()
                conf_source.save()

                if notify:
                    self.notify(source.id)

            except Exception as e:
                self.logger.exception("Error fetching AWT http/gsm collar data")

    def _transform(self, item):
        source, o = item

        side_data = dict((k, o.__getattribute__(k)) for k in ('speed', 'heading', 'temperature', 'height'))
        return Obs(source=source, recorded_at=o.recorded_at, latitude=o.latitude, longitude=o.longitude,
                   additional=side_data)



