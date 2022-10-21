
import requests
from requests.auth import HTTPBasicAuth
from functools import namedtuple
import copy
import io

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

import datetime
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz

import logging
from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericRelation

from tracking.models.plugin_base import Obs, TrackingPlugin, DasDefaultTarget, SourcePlugin
from observations.models import Source, SubjectSource, Subject

from tracking.pubsub_registry import notify_new_tracks


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
Fix = namedtuple('Fix', ['collar_id', 'longitude', 'latitude',
                         'recorded_at', 'speed', 'heading', 'temperature', 'height'])
field_transform = (str, float, float, __str2date, float, float, str, int)

HEARTBEAT_ESN = '300034012609560'
API_XMLNS = '{https://www.aff.gov/affSchema}'


def _qualify(s):
    return '{}{}'.format(API_XMLNS, s)


def _unqualify(s):
    return s.replace(API_XMLNS, '')


class SpiderTracksClient(object):

    # https://go.spidertracks.com/api/aff/feed

    def __init__(self, service_api=None, username=None, password=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.username = username
        self.password = password
        self.service_api = service_api or 'https://go.spidertracks.com/api/aff/feed'

    def fetch_observations(self, start_time):

        data = self._get_data(start_time)

        def _dictify(elem, doc=None):
            doc = doc or {}
            doc['attrib'] = elem.attrib
            doc['text'] = elem.text.strip() if elem.text else ''

            for child in elem:
                doc.setdefault(_unqualify(child.tag), []
                               ).append(_dictify(child))
            return doc

        try:
            for event, elem in etree.iterparse(io.StringIO(data)):
                if event == 'end' and elem.tag == (_qualify('acPos')):
                    item = _dictify(elem)
                    yield item
                    elem.clear()

        except Exception as e:
            self.logger.exception('')

    def _get_data(self, start_time):
        '''
        Get a query response as text.
        :param start_time: the time after which we want to see fixes.
        :return: a string, or None
        '''
        parameters = {'start_time': start_time.isoformat(),
                      'report_time': datetime.datetime.now(tz=pytz.utc).isoformat()
                      }
        payload = '''<?xml version="1.0" encoding="utf-8"?>
            <data xmlns="https://aff.gov/affSchema" sysId="DAS" rptTime="{report_time}" version="2.23">
              <msgRequest to="spidertracks" from="DAS" msgType="Data Request" subject="Async" dateTime="{start_time}">
                <body>{start_time}</body>
              </msgRequest>
            </data>
        '''.format(**parameters)

        headers = {
            'content-type': "application/xml",
            'cache-control': "no-cache"
        }

        response = requests.request("POST", self.service_api, data=payload, headers=headers,
                                    auth=HTTPBasicAuth(self.username, self.password))

        if response and response.status_code == 200:
            return response.text


DEFAULT_ASSIGNED_RANGE = list((datetime.datetime(1970, 1, 1, tzinfo=pytz.utc),
                               datetime.datetime.max.replace(tzinfo=pytz.utc)))


class SpiderTracksPlugin(TrackingPlugin):
    '''
    Fetch data from Savannah Tracking API.
    '''
    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=2)
    SOURCE_TYPE = 'tracking-device'
    DEFAULT_MODEL_NAME = 'spidertracker'

    service_username = models.CharField(max_length=50,
                                        help_text='The username for querying the SpiderTracks service.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for querying the SpiderTracks service.')
    service_api = models.CharField(max_length=100,
                                   help_text='The API endpoint for the SpiderTracks web-service.')

    source_plugin_reverse_relation = 'spidertracksplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')


    @property
    def run_source_plugins(self):
        return False

    def execute(self):

        notify_these = set()

        with DasDefaultTarget() as t:
            for observation in self.fetch():
                notify_these.add(observation.source.id)
                t.send(observation)
        self.save()

        (notify_new_tracks(sid) for sid in notify_these)

    def fetch(self):

        self.logger = logging.getLogger(self.__class__.__name__)

        client = SpiderTracksClient(username=self.service_username,
                                    password=self.service_password,
                                    service_api=self.service_api)

        try:
            st = parse_date(self.additional['latest_timestamp'])
        except Exception as e:
            st = datetime.datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        source_map = dict((source.manufacturer_id, source) for source in
                          [sp.source for sp in self.source_plugins.all()])

        lt = None
        for fix in client.fetch_observations(start_time=st):
            try:

                fix_time = parse_date(fix['attrib']['dateTime'])

                if self._pass_filter(fix):

                    manufacturer_id = fix['attrib']['esn']
                    if manufacturer_id in source_map:
                        source = source_map.get(manufacturer_id)
                    else:
                        source = Source.objects.ensure_source(source_type=self.SOURCE_TYPE,
                                                              provider=self.provider.provider_key,
                                                              manufacturer_id=manufacturer_id,
                                                              model_name=self.DEFAULT_MODEL_NAME,
                                                              subject={
                                                                  'subject_subtype_id': 'plane',
                                                                  'name': self._get_registration(fix) or manufacturer_id
                                                              }
                                                              )

                        source_map[manufacturer_id] = source

                    observation = self._transform(fix, source)
                    if observation:
                        yield observation

                # keep track of latest timestamp.
                lt = max(lt, fix_time) if lt else fix_time
            except Exception as e:
                self.logger.exception('processing spidertracks.')

        if lt:  # Update cursor data.
            self.additional['latest_timestamp'] = lt.isoformat()

    def _pass_filter(self, fix):
        return (not fix['attrib']['esn'] == HEARTBEAT_ESN)

    def _get_registration(self, fix):
        for item in fix.get('telemetry', []):
            if item['attrib']['name'] == 'registration':
                return item['attrib']['value']

    def _transform(self, fix, source):

        recorded_at = parse_date(fix['attrib']['dateTime'])
        manufacturer_id = fix['attrib']['esn']

        latitude = float(fix['Lat'][0]['text'])
        longitude = float(fix['Long'][0]['text'])

        # Reasonable defaults
        registration = manufacturer_id
        track_id = ''

        for item in fix.get('telemetry', []):
            if item['attrib']['name'] == 'registration':
                registration = item['attrib']['value']
            if item['attrib']['name'] == 'trackid':
                track_id = item['attrib']['value']

        side_data = dict((k, fix.get(k))
                         for k in ('speed', 'heading', 'altitude',))
        side_data['track_id'] = track_id
        side_data['registration'] = registration

        # Set subject_name in additional to trigger updating Subject.name.
        side_data['subject_name'] = registration

        return Obs(source=source, recorded_at=recorded_at, latitude=latitude, longitude=longitude,
                   additional=side_data)
