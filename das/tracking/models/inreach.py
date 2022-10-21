import re
import copy
import http.client
import urllib.parse
from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericRelation

import datetime
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz
import json
import base64
import logging
import requests

from tracking.models.plugin_base import Obs, TrackingPlugin, SourcePlugin


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

        conn = http.client.HTTPSConnection(self.host)

        start_ts = kwargs.get(
            'after', (datetime.datetime.now() - timedelta(days=31)))
        end_ts = start_ts + timedelta(days=60)
        payload = {
            'IMEIs': imei,
            'Start': start_ts.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'End': end_ts.strftime('%Y-%m-%dT%H:%M:%SZ')
        }

        qs = urllib.parse.urlencode(payload)

        headers = {'accept': "*/*",
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
            self.logger.debug(
                'Failed to get good response from Inreach API. [%s %s]', res.status, res.reason)

    @classmethod
    def parse_line(cls, s, **kwargs):
        '''
        Transforms a History item to an Observation
        :param s:
        :return:
        '''

        (ts, offset) = re.match(
            r'/Date\((\d{13})-?(\d{4})?\)/', s.pop('Timestamp')).groups()
        ts = float(ts) / 1000

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

    service_username = models.CharField(max_length=50,
                                        help_text='The username for querying the InReach API service.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for querying the InReach API service.')
    service_api_host = models.CharField(max_length=50,
                                        help_text='the ip-address or host-name for the InReach API service.')

    source_plugin_reverse_relation = 'inreachplugin'

    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    DEFAULT_START_OFFSET = timedelta(days=31)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)

    class Meta:
        verbose_name = "inReach Professional plugin"
        verbose_name_plural = "inReach Professional plugins"

    def should_run(self, source_plugin):

        # Don't bother running now if less than 20 minutes has passed since the
        # latest fix.
        try:
            latest_timestamp = source_plugin.cursor_data.get(
                'latest_timestamp')
            if not latest_timestamp:
                return True
            latest_timestamp = parse_date(latest_timestamp)

            if (datetime.now(tz=pytz.UTC) - self.DEFAULT_REPORT_INTERVAL) > latest_timestamp:
                return True

        except Exception as e:
            return True
        else:
            return False

    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        self.client = InreachClient(host=self.service_api_host,
                                    username=self.service_username,
                                    password=self.service_password)

        try:
            default_starttime = datetime.datetime.now(
                tz=pytz.utc) - self.DEFAULT_START_OFFSET
            _ = self.cursor_data['latest_timestamp']
            latest_ts = parse_date(_)
            latest_ts = max(default_starttime, latest_ts)

        except KeyError:
            self.cursor_data = self.cursor_data or {}
            latest_ts = default_starttime

        self.logger.debug("Fetching data for manufacturer_id %s after %s" % (
            source.manufacturer_id, latest_ts))

        for observation in self.client.fetch_observations(imei=source.manufacturer_id, after=latest_ts):
            latest_ts = max(latest_ts, observation['recorded_at'])
            yield self._transform(source, observation)

        self.logger.debug(
            "Saving latest timestamp for source %s at %s", source.manufacturer_id, latest_ts)
        self.cursor_data['latest_timestamp'] = latest_ts.isoformat()

    def _transform(self, source, observation):

        # Copy any none-standard fields into Obs.additional
        side_data = dict((k, observation.get(k))
                         for k in observation.keys() if k not in Obs._fields)
        return Obs(source=source, recorded_at=observation.get('recorded_at'),
                   latitude=observation.get('latitude'),
                   longitude=observation.get('longitude'),
                   additional=side_data)

    def _maintenance(self):

        # cur = observations.models.Subject.objects.all()
        #
        # for sub in cur:
        #     sub.additional['rgb'] = gen_random_rgb()
        #     sub.save()

        self._sync_unit_info()

    def _sync_unit_info(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        u = self.additional['account_username']
        p = self.additional['account_password']
        ac = InreachAccountClient(username=u, password=p)

        for dev in ac.fetch_devices():
            print(dev)
            try:
                src = ensure_source(dev)

                ensure_source_plugin(src, self)
                ts = str2date(dev['ActivationDate'])
                ensure_subject_source(src, ts, dev['DeviceName'])

            except Exception as e:
                self.logger.exception('Error in maintenance')


import random


def gen_random_rgb():
    return ','.join([str(random.randint(0, 255)) for i in range(3)])


from observations.models import Subject, SubjectSource, Source
from django.contrib.contenttypes.models import ContentType
from tracking.models import SourcePlugin


def str2date(d, default_tzinfo=pytz.UTC):
    '''Parse a date and if it's naive, replace tzinfo with default_tzinfo.'''
    dt = parse_date(d)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tzinfo)
    return dt

# Helper functions for hydrating Source and Subject for the given message.


def ensure_source(inreach_device):
    src, created = Source.objects.get_or_create(source_type='gps-radio',
                                                manufacturer_id=inreach_device['IMEI'],
                                                defaults={'model_name': 'type:{}, product:{}'.format(inreach_device['Type'], inreach_device['Product']),
                                                          'additional': {'note': 'Created automatically during maintenance.'}})

    return src


def ensure_source_plugin(source, tracking_plugin):

    defaults = dict(
        status='enabled',
        # cursor_data={}
    )

    plugin_type = ContentType.objects.get_for_model(tracking_plugin)
    v, created = SourcePlugin.objects.get_or_create(defaults=defaults,
                                                    source=source,
                                                    plugin_id=tracking_plugin.id,
                                                    plugin_type=plugin_type)

    return v


def ensure_subject_source(source, event_time, subject_name=None):
    # get the most recent Subject for this Source
    subject_source = SubjectSource \
        .objects \
        .filter(source=source, assigned_range__contains=event_time)\
        .order_by('assigned_range')\
        .reverse()\
        .first()

    if not subject_source:

        subject_name = subject_name or 'inreach-{}'.format(
            source.manufacturer_id)

        sub, created = Subject.objects.get_or_create(
            subject_subtype_id='ranger',
            name=subject_name,
            defaults=dict(additional=dict(region='', country='', ))
        )

        d1 = pytz.utc.localize(datetime.datetime.min)
        d2 = pytz.utc.localize(datetime.datetime.max)
        if sub:
            subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                          defaults=dict(assigned_range=(d1, d2), additional={
                                                                              'note': 'Created automatically during feed sync.'}))

    return subject_source


class InreachAccountClient(BasicAuthClient):

    def __init__(self, username=None, password=None, host='account-api.delorme.com'):
        self.logger = logging.getLogger(self.__class__.__name__)

        self.host = host
        self.username = username
        self.password = password

    def fetch_users(self):

        conn = http.client.HTTPSConnection(self.host)

        headers = {'authorization': super(
            InreachAccountClient, self).auth_header()}

        conn.request("GET", "/V1/Users", headers=headers)

        res = conn.getresponse()
        data = res.read()

        if res and res.status == http.client.OK:
            res = json.loads(data.decode("utf-8"))
            yield from res['Users']

    def fetch_devices(self):

        conn = http.client.HTTPSConnection(self.host)

        headers = {'authorization': super(
            InreachAccountClient, self).auth_header()}

        conn.request("GET", "/V1/Devices", headers=headers)

        res = conn.getresponse()
        data = res.read()

        if res and res.status == http.client.OK:
            res = json.loads(data.decode("utf-8"))
            yield from res['Devices']

    def user_for_device(self, imei):
        conn = http.client.HTTPSConnection(self.host)

        headers = {'authorization': super(
            InreachAccountClient, self).auth_header()}

        params = {'imei': imei}
        r = requests.get('https://%s/V1/Users' %
                         self.host, params=params, headers=headers)

        if r.status_code == requests.codes.ok:

            data = r.text

            data = data.decode('utf-8') if hasattr(data, 'decode') else data
            res = json.loads(data)
            yield from res['Users']
