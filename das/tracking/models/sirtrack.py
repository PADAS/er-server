import io
import http.client
import requests
import zipfile
import re
from functools import namedtuple
import copy
import urllib.request
import urllib.parse
import urllib.error

import datetime
import time
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz

import logging
from django.contrib.gis.db import models

import fastkml
import json

from tracking.models.plugin_base import Obs, TrackingPlugin, DasDefaultTarget
from tracking.pubsub_registry import notify_new_tracks

from observations.models import Source, SubjectSource, Subject


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
# Fix = namedtuple('Fix', ['collar_id', 'longitude', 'latitude', 'recorded_at', 'speed', 'heading', 'temperature', 'height'])
# field_transform = (str, float, float, __str2date, float, float, str, int)

def parse_cookie(cookie):
    items = [_.split('=') for _ in cookie.split(';')]
    cookies = dict(items)
    return cookies


def split_link(url):
    url, qs = url.split('?')
    params = dict([p.split('=') for p in qs.split('&')])
    return (url, params)


def get_kml(url, params):
    """
    Get kml and return raw contents.
    """
    headers = {
        'cache-control': "no-cache",
    }

    headers = None
    response = requests.request(
        "GET", url, headers=headers, params=params, verify=False)

    if response.status_code != 200:
        return None

    try:
        bf = io.BytesIO(response.content)
        kmz = zipfile.ZipFile(bf, 'r')
        for name in kmz.namelist():
            kmlbytes = kmz.read(name)
        return kmlbytes
    except:
        return response.content


class SirTrackClient(object):

    def __init__(self, service_api=None, username=None, password=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.username = username
        self.password = password
        self.service_api = service_api

    def login(self):
        service_root = 'https://data.sirtrack.com/json-rpc/'
        login_data = {'id': 2,
                      'method': 'loginFrontService.login',
                      'params': [self.username, self.password]
                      }

        result = requests.post(service_root, data=json.dumps(login_data))

        if result.status_code == 200:
            cookies = parse_cookie(result.headers['Set-Cookie'])
            return cookies
        else:
            print('Unable to log in.')
            print('result.code: %s, result.data: %s' %
                  (result.status_code, result.data))

    def get_projects(self, cookies):

        cookie_val = '{}={}'.format(
            'vosao_session', cookies.get('vosao_session'))
        projects = requests.get('https://data.sirtrack.com/restlet/projects?_={}'.format(int(time.time() * 1000)),
                                headers=dict(cookie=cookie_val))

        projects_data = json.loads(projects.text)
        print('projects data: %s' % (projects_data,))

        return projects_data

    def download_csv_files(self, projects_data):
        # Fetch the top-level KML document from Sirtrack and use its NetworkLinks to download
        # CSV files of track data.
        for pd in projects_data:
            kml_url = 'https://data.sirtrack.com/restlet/geo/{id}/{name}.kmz'.format(
                **pd)
            kmldata = get_kml(kml_url, params=dict(key=pd['geoJsonKey']))

            if not kmldata:
                self.logger.exception(
                    'Failed to download KML at %s' % (kml_url,))
                raise Exception('Failed to download KML at %s' % (kml_url,))

            k = fastkml.kml.KML()
            k.from_string(kmldata)

            for f in k.features():
                if hasattr(f, 'link'):
                    csv_link = f.link.replace('.kmz', '.csv')
                    try:
                        (filename, httpmessage) = urllib.request.urlretrieve(csv_link)
                        yield filename, httpmessage
                    except urllib.request.HTTPError as e:
                        self.logger.error(
                            'Failed to download SirTrack data at %s', csv_link)

    def parsefile(filename):

        with open(filename, 'r') as fo:

            line = fo.readline()
            keys = line.strip().split(',')

            # Scrub the keys a little.
            keys = [re.sub('[^a-zA-Z0-9]', '_', k).strip('_').lower()
                    for k in keys]

            line = fo.readline()
            while line:
                item = dict(zip(keys, line.strip().split(',')))
                if item['longitude'] and item['latitude']:
                    yield item
                line = fo.readline()

    def fetch_observations(self):

        login_cookies = self.login()
        projects_data = self.get_projects(login_cookies)

        if not projects_data:
            return

        for filename, httpmessage in self.download_csv_files(projects_data):

            if filename and httpmessage.code == 200:
                yield from self.parsefile(filename)


class SirtrackPlugin(TrackingPlugin):
    '''
    Fetch data from SirTrack API.
    '''
    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=30)

    service_username = models.CharField(max_length=50,
                                        help_text='The username for querying the SirTrack service.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for querying the SirTrack service.')
    service_api = models.CharField(max_length=50,
                                   help_text='The API endpoint for SirTrack data.')

    DEFAULT_SUBJECT_TYPE = 'wildlife'
    DEFAULT_SUBJECT_SUBTYPE = 'cheetah'
    DEFAULT_SOURCE_TYPE = 'tracking-device'
    DEFAULT_MODEL_NAME = 'Lotek'

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

        # If these are indicated in the 'additional' blob, the use them.
        defaults = self.additional.get('defaults', {})
        default_subject_type = defaults.get(
            'subject_type', self.DEFAULT_SUBJECT_TYPE)
        default_subject_subtype = defaults.get(
            'subject_subtype', self.DEFAULT_SUBJECT_SUBTYPE)
        default_source_type = defaults.get(
            'source_type', self.DEFAULT_SOURCE_TYPE)
        default_model_name = defaults.get(
            'model_name', self.DEFAULT_MODEL_NAME)

        self.logger = logging.getLogger(self.__class__.__name__)

        client = SirTrackClient(username=self.service_username,
                                password=self.service_password,
                                service_api=self.service_api)

        try:
            st = parse_date(self.additional['latest_timestamp'])
        except Exception as e:
            st = datetime.datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        source_map = dict((source.manufacturer_id, source) for source in
                          [sp.source for sp in self.source_plugins.all()])

        lt = None
        for fix in client.fetch_observations():
            try:

                fix_time = parse_date('{utc_date} {utc_time}'.format(**fix))
                if fix_time < st:
                    continue

                if self._pass_filter(fix):

                    manufacturer_id = fix['tag_id']
                    if manufacturer_id in source_map:
                        source = source_map.get(manufacturer_id)
                    else:
                        source = Source.objects.ensure_source(source_type=default_source_type,
                                                              provider=self.provider.name,
                                                              manufacturer_id=manufacturer_id,
                                                              model_name=default_model_name,
                                                              subject={
                                                                  'subject_type': default_subject_type,
                                                                  'subject_subtype': default_subject_subtype,
                                                                  'name': fix.get('tag_name') or manufacturer_id
                                                              }
                                                              )

                        source_map[manufacturer_id] = source

                    observation = self._transform(fix, source)
                    if observation:
                        yield observation

                # keep track of latest timestamp.
                lt = max(lt, fix_time) if lt else fix_time
            except Exception as e:
                self.logger.exception('processing SirTrack.')

        if lt:  # Update cursor data.
            self.additional['latest_timestamp'] = lt.isoformat()

    def _pass_filter(self, fix):
        return True

    def _transform(self, fix, source):

        recorded_at = parse_date('{utc_date} {utc_time}'.format(**fix))
        latitude = float(fix['latitude'])
        longitude = float(fix['longitude'])

        side_data = dict((k, fix.get(k))
                         for k in fix.keys() - set(('latitude', 'longitude',)))
        return Obs(source=source, recorded_at=recorded_at, latitude=latitude, longitude=longitude,
                   additional=side_data)
