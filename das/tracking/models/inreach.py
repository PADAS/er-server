import re
import copy
import http.client
import urllib.parse
from django.contrib.gis.db import models
import datetime
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz
import json
import base64
import logging
import requests

from tracking.models.plugin_base import Obs, TrackingPlugin

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


class InreachClient(BasicAuthClient):

    def __init__(self, host=None, username=None, password=None):
        self.logger = logging.getLogger(self.__class__.__name__)

        self.host = host
        self.username = username
        self.password = password

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


class InreachPlugin(TrackingPlugin):
    '''
    Inreach plugin fetches data from explorer.delorme.com for radios we've set up in DAS. Data read from Delorme's
    service is entered in DAS as observations.
    '''

    service_user_id = models.CharField(max_length=50,
                                       help_text='The username for querying the InReach API service.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for querying the InReach API service.')
    service_api_host = models.CharField(max_length=50,
                                        help_text='the ip-address or host-name for the InReach API service.')

    DEFAULT_START_OFFSET = timedelta(days=31)

    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        self.client = InreachClient(host=self.service_api_host,
                                    username=self.service_user_id,
                                    password=self.service_password)

        try:
            default_starttime = datetime.datetime.now(tz=pytz.utc) - self.DEFAULT_START_OFFSET
            _ = self.cursor_data['latest_timestamp']
            latest_ts = parse_date(_)
            latest_ts = max(default_starttime, latest_ts)

        except KeyError:
            self.cursor_data = self.cursor_data or {}
            latest_ts = default_starttime

        self.logger.debug("Fetching data for manufacturer_id %s after %s" % (source.manufacturer_id, latest_ts))

        for observation in self.client.fetch_observations(imei=source.manufacturer_id, after=latest_ts):
            latest_ts = max(latest_ts, observation['recorded_at'])
            yield self._transform(source, observation)

        self.logger.debug("Saving latest timestamp for source %s at %s", source.manufacturer_id, latest_ts)
        self.cursor_data['latest_timestamp'] = latest_ts.isoformat()

    def _transform(self, source, observation):

        # Copy any none-standard fields into Obs.additional
        side_data = dict((k, observation.get(k)) for k in observation.keys() if k not in Obs._fields)
        return Obs(source=source, recorded_at=observation.get('recorded_at'),
                   latitude=observation.get('latitude'),
                   longitude=observation.get('longitude'),
                   additional=side_data)


class InreachAccountClient(BasicAuthClient):

    def __init__(self, host=None, username=None, password=None):
        self.logger = logging.getLogger(self.__class__.__name__)

        self.host = host
        self.username = username
        self.password = password

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
