"""
 Fetch and transform Savannah data into DAS input format
"""
import copy
import re
import http.client
import urllib.parse
from observations.models import Observation, Source
from .plugin import DasPlugin, PluginTarget
import datetime, time
from datetime import timedelta
from data_input.models import PluginConf, PluginConfSource

from dateutil.parser import parse as parse_date
import pytz
import json
import base64

def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
field_names = ('lat', 'lon', 'brightness', 'scan', 'track', 'acq_date', 'acq_time', 'satellite', 'confidence', 'version', 'bright_t31', 'frp')
field_transform = (float, float, float, float, float, str, str, str, int, str, float, float)


# class SavannaException(Exception):
#     pass

class InreachClient(object):

    def __init__(self, config={}):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''
        self.host = config.get('host', 'explore.delorme.com')
        self.username = config.get('username', 'vulcan_das')
        self.password = config.get('password', '5oBt1F27Pw9S')


    def __auth_header(self):
        auth = '%s:%s' % (self.username, self.password)
        auth = base64.b64encode(bytes(auth, 'utf8'))
        return 'Basic {}'.format(auth.decode('utf8'))

    def fetch_observations(self, imei=None, **kwargs):

        '''
        :param region_id:
        :param kwargs:
        :return:
        '''

        conn = http.client.HTTPSConnection('explore.delorme.com')

        start_ts = kwargs.get('after', (datetime.datetime.now() - timedelta(days=31)))
        payload = {
            'IMEIs': imei,
            'Start': start_ts.strftime('%Y-%m-%dT%H:%M:%S'),
            'End': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        }

        qs = urllib.parse.urlencode(payload)


        headers = { 'accept': "*/*",
                    'content-type': 'application/json',
                    'Authorization': self.__auth_header()
                    }

        path = '/ipcinbound/V1/Location.svc/History?{}'.format(qs)
        conn.request('GET', path, None, headers)

        res = conn.getresponse()
        if res.status == http.client.OK:
            data = res.read()
            data = json.loads(data.decode())

            for h in data['HistoryItems']:
                yield self.__class__.parse_line(h)

        else:
            print(res.status, res.reason)
            print(res)

    @classmethod
    def parse_line(cls, s, **kwargs):
        '''
        Transforms a History item to an Observation
        :param s:
        :return:
        '''

        (ts, offset) = re.match(r'/Date\((\d{13})-?(\d{4})?\)/', s.pop('Timestamp')).groups()
        ts = float(ts)/1000

        s['ts'] = datetime.datetime.fromtimestamp(ts, tz=pytz.utc)
        coordinate = s.pop('Coordinate', {'Latitude': 0.0, 'Longitude': 0.0})
        if coordinate:
            s['lat'] = coordinate['Latitude']
            s['lon'] = coordinate['Longitude']
        return s


def unixtimestamp(d):
    return int(time.mktime(d.timetuple()))



class InreachPlugin(DasPlugin):

    def __init__(self, plugin_conf, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self._config = plugin_conf
        self.client = InreachClient(config=self._config.configuration)

    def _fetch(self):

        sources = Source.objects.filter(source_type='inreach')
        for source in sources:

            default_timestamp = datetime.datetime.now(tz=pytz.utc) - timedelta(days=31)
            latest_ts = default_timestamp
            try:
                pcs = PluginConfSource.objects.get(source=source, plugin_conf=self._config)
                _ = pcs.additional.get('latest_timestamp', None)
                try:
                    latest_ts = parse_date(_)
                except:
                    latest_ts = default_timestamp

            except PluginConfSource.DoesNotExist:
                pcs = PluginConfSource(source=source, plugin_conf=self._config, additional=dict(latest_timestamp=default_timestamp))
                pcs.save()

            print("Fetching data for manufacturer_id %s after %s" % (source.manufacturer_id,latest_ts))
            for observation in self.client.fetch_observations(imei=source.manufacturer_id, after=latest_ts):
                latest_ts = max(latest_ts, observation['ts'])
                yield (source, observation)

            pcs.additional['latest_timestamp'] = latest_ts
            pcs.save()


    def _transform(self, so_tuple):
        source, observation = so_tuple
        return (source, observation)

    def execute(self):
        super().execute()


class InreachTarget(PluginTarget):

    def _handle_item(self, item):
        (source, obs) = item
        Observation.objects.add_observation(source, obs)
        print(obs)


