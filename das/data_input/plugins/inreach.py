"""
 Fetch and transform Savannah data into DAS input format
"""
import copy
import re
import http.client
import urllib.parse
from observations.models import Observation, Source
from .plugin import DasPlugin, PluginTarget, DasPluginConfigurationError
import datetime, time
from datetime import timedelta
from data_input.models import PluginConf, PluginConfSource

from dateutil.parser import parse as parse_date
import pytz
import json
import base64
import logging

def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)

class BasicAuthClient(object):

    def auth_header(self):
        auth = '%s:%s' % (self.username, self.password)
        auth = base64.b64encode(bytes(auth, 'utf8'))
        return 'Basic {}'.format(auth.decode('utf8'))

class InreachException(Exception):
    pass

class InreachAccountClient(BasicAuthClient):

    def __init__(self, config=None):
        self._config = config or {}

        self._config = config or {}
        if not all(x in self._config for x in ('host', 'username', 'password')):
            raise DasPluginConfigurationError('Not enough configuration provided.')

        self.logger = logging.getLogger(self.__class__.__name__)

        self.host = self._config.get('host')
        self.username = self._config.get('username')
        self.password = self._config.get('password')

    def fetch_users(self):

        conn = http.client.HTTPSConnection(self.host)

        headers = {'authorization': super(InreachAccountClient, self).auth_header()}

        conn.request("GET", "/V1/Users", headers=headers)

        res = conn.getresponse()
        data = res.read()

        if res and res.status == http.client.OK:
            res = json.loads(data.decode("utf-8"))
            yield from res['Users']


class InreachClient(BasicAuthClient):

    def __init__(self, config=None):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''
        self._config = config or {}
        if not all(x in self._config for x in ('host', 'username', 'password')):
            raise DasPluginConfigurationError('Not enough configuration provided.')


        self.host = self._config.get('host')
        self.username = self._config.get('username')
        self.password = self._config.get('password')

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
                    'Authorization': super(InreachClient, self).auth_header()
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
            self.logger.debug('Failed to get good response from Inreach API. [%s %s]', res.status, res.reason)

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
    '''
    Inreach plugin fetches data from explorer.delorme.com for radios we've set up in DAS. Data read from Delorme's
    service is entered in DAS as observations.
    '''
    def __init__(self, plugin_conf, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self._config = plugin_conf
        self.client = InreachClient(config=self._config.configuration)
        self.logger = logging.getLogger(InreachPlugin.__name__)

    def _fetch(self):

        pcslist = PluginConfSource.objects.filter(plugin_conf=self._config)

        for pcs in pcslist:
            try:
                _ = pcs.additional.get('latest_timestamp', None)
                latest_ts = parse_date(_)
            except AttributeError:
                latest_ts = datetime.datetime.now(tz=pytz.utc) - timedelta(days=31)

            self.logger.debug("Fetching data for manufacturer_id %s after %s" % (pcs.source.manufacturer_id, latest_ts))
            for observation in self.client.fetch_observations(imei=pcs.source.manufacturer_id, after=latest_ts):
                latest_ts = max(latest_ts, observation['ts'])
                yield (pcs.source, observation)

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


class InreachAccountPlugin(DasPlugin):


    def __init__(self, plugin_conf, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self._config = plugin_conf
        self.client = InreachAccountClient()
        self.logger = logging.getLogger(InreachAccountPlugin.__name__)

    def _fetch(self):

        source = None
        self.logger.debug("Fetching data for Inreach account...")
        for observation in self.client.fetch_users():
            yield (source, observation)



    def _transform(self, so_tuple):
        source, observation = so_tuple
        return (source, observation)

    def execute(self):
        super().execute()


class InreachAccountTarget(PluginTarget):

    def _handle_item(self, item):
        (source, obs) = item


