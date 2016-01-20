"""
 Fetch and transform Savannah data into DAS input format
"""
import copy
import re
import http.client
import urllib.parse
from observations.models import Observation
from .plugin import DasPlugin, Obs, DasPluginConfigurationError
import datetime, time
from datetime import timedelta
from data_input.models import PluginConf, PluginConfSource

from dateutil.parser import parse as parse_date
import pytz
import json
import base64
import logging
import requests

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

    def fetch_devices(self):

        conn = http.client.HTTPSConnection(self.host)

        headers = {'authorization': super(InreachAccountClient, self).auth_header()}

        conn.request("GET", "/V1/Devices", headers=headers)

        res = conn.getresponse()
        data = res.read()

        if res and res.status == http.client.OK:
            res = json.loads(data.decode("utf-8"))
            yield from res['Devices']

    def user_for_device(self, imei):
        conn = http.client.HTTPSConnection(self.host)

        headers = {'authorization': super(InreachAccountClient, self).auth_header()}

        params = {'imei' : imei}
        r = requests.get('https://%s/V1/Users' % self.host, params=params, headers=headers)

        if r.status_code == requests.codes.ok:

            data = r.text

            data = data.decode('utf-8') if hasattr(data, 'decode') else data
            res = json.loads(data)
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

            for h in reversed(data['HistoryItems']):
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

        s['recorded_at'] = datetime.datetime.fromtimestamp(ts, tz=pytz.utc)
        coordinate = s.pop('Coordinate', {'Latitude': 0.0, 'Longitude': 0.0})
        if coordinate:
            s['latitude'] = coordinate['Latitude']
            s['longitude'] = coordinate['Longitude']

        s['elevation'] = s.pop('Altitude', None)

        return s


def unixtimestamp(d):
    return int(time.mktime(d.timetuple()))



class InreachPlugin(DasPlugin):
    '''
    Inreach plugin fetches data from explorer.delorme.com for radios we've set up in DAS. Data read from Delorme's
    service is entered in DAS as observations.
    '''

    plugin_key = 'inreach-api'

    def initConfig(self):
        self.client = InreachClient(config=self.config.configuration)


    def _fetch(self):

        pcslist = PluginConfSource.objects.filter(plugin_conf=self.config)

        for pcs in pcslist:
            try:
                default_starttime = datetime.datetime.now(tz=pytz.utc) - timedelta(days=31)
                _ = pcs.additional.get('latest_timestamp', None)
                latest_ts = parse_date(_)

                latest_ts = max(default_starttime, latest_ts)

            except AttributeError:
                latest_ts = default_starttime

            self.logger.debug("Fetching data for manufacturer_id %s after %s" % (pcs.source.manufacturer_id, latest_ts))

            notify = False
            for observation in self.client.fetch_observations(imei=pcs.source.manufacturer_id, after=latest_ts):
                latest_ts = max(latest_ts, observation['recorded_at'])
                yield (pcs.source, observation)
                notify = True

            self.logger.debug("Saving latest timestamp for source %s at %s", pcs.source.manufacturer_id, latest_ts)
            pcs.additional['latest_timestamp'] = latest_ts.isoformat()
            pcs.save()

            if notify:
                self.notify(pcs.source.id)



    def _transform(self, so_tuple):
        source, o = so_tuple

        # Copy any none-standard fields into Obs.additional
        side_data = dict((k, o.get(k)) for k in o.keys() if k not in Obs._fields)
        return Obs(source=source, recorded_at=o.get('recorded_at'),
                   latitude=o.get('latitude'),
                   longitude=o.get('longitude'),
                   additional=side_data)

    def execute(self):
        super().execute()


class InreachAccountPlugin(DasPlugin):


    def initConfig(self):
        self.client = InreachAccountClient()

    def _fetch(self):

        source = None
        self.logger.debug("Fetching data for Inreach account...")
        for observation in self.client.fetch_users():
            yield (source, observation)

    def _transform(self, so_tuple):
        source, observation = so_tuple
        return (source, observation)




