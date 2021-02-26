from functools import namedtuple
import datetime
import copy
from datetime import timedelta
import requests
from dateutil.parser import parse as parse_date
import pytz
import logging

from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericRelation

from tracking.models.plugin_base import Obs, TrackingPlugin, SourcePlugin

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

    def __init__(self, api_url=None):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''
        self.logger = logging.getLogger(self.__class__.__name__)
        self.api_url = api_url


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

        try:
            r = requests.get(self.api_url, params=params, headers=headers, timeout=5.0)
        except requests.exceptions.Timeout:
            self.logger.warning('Timeout when fetching data for collar_id: %s', collar_id)
        else:
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




class AWTHttpPlugin(TrackingPlugin):

    service_api_url = models.URLField(help_text='The URL for the AWT service.',
                                      default='http://www.yrless.co.za/STE/yrserv/datanew.phtml')
    DEFAULT_START_OFFSET = timedelta(days=7)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)

    source_plugin_reverse_relation = 'awthttpplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        self.client = AWTHttpClient(api_url=self.service_api_url)

        try:
            st = parse_date(self.cursor_data['latest_timestamp'])
        except:
            st = datetime.datetime.utcnow() - self.DEFAULT_START_OFFSET

        lt = st
        st = st + timedelta(seconds=1)

        self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)
        for fix in self.client.fetch_observations(source.manufacturer_id, start_time=st):
            lt = fix.recorded_at
            yield self._transform(source, fix)

        self.cursor_data['latest_timestamp'] = lt.isoformat()

    @staticmethod
    def _transform(source, item):

        side_data = dict((k, item.__getattribute__(k)) for k in ('speed', 'heading', 'temperature', 'height'))
        return Obs(source=source, recorded_at=item.recorded_at, latitude=item.latitude, longitude=item.longitude,
                   additional=side_data)



