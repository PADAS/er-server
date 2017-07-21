import io
import requests
import zipfile
import re
import datetime
import time
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz
import json

import logging

import fastkml

from django.contrib.gis.db import models

from tracking.models.plugin_base import Obs, TrackingPlugin, DasDefaultTarget
from tracking.pubsub_registry import notify_new_tracks

from tracking.models.utils import split_link, parse_cookie
from observations.models import Source

logger = logging.getLogger(__name__)


# SirTrack server may be a little slow, so using a long timeout for first byte.
DEFAULT_REQUEST_TIMEOUT = (1, 10)  # seconds for (connect, read)
CSV_REQUEST_TIMEOUT = (1, 10)  # seconds


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

        result = requests.post(service_root, data=json.dumps(
            login_data), timeout=DEFAULT_REQUEST_TIMEOUT)

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
                                headers=dict(cookie=cookie_val), timeout=DEFAULT_REQUEST_TIMEOUT)

        projects_data = json.loads(projects.text)
        print('projects data: %s' % (projects_data,))

        return projects_data

    def get_csv_links(self, projects_data):
        # Fetch the top-level KML document from Sirtrack and use its NetworkLinks to download
        # CSV files of track data.

        if not projects_data:
            return

        for pd in projects_data:
            kml_url = 'https://data.sirtrack.com/restlet/geo/{id}/{name}.kmz'.format(
                **pd)
            kmldata = self.get_kml(kml_url, params=dict(key=pd['geoJsonKey']))

            if not kmldata:
                self.logger.exception(
                    'Failed to download KML at %s' % (kml_url,))
                raise Exception('Failed to fetch KML at %s' % (kml_url,))

            k = fastkml.kml.KML()
            k.from_string(kmldata)

            for f in k.features():
                if hasattr(f, 'link'):
                    yield f.link.replace('.kmz', '.csv').replace(' ', '+')

    def parse_csv_link(self, link):
        '''
        Read chunked response as a CSV file and yield a dictionary for each row.
        :param link: A link to a CSV file.
        :return: generate records as dict() objects, using CSV headers as keys.
        '''

        response = None
        try:

            response = requests.get(
                link, timeout=CSV_REQUEST_TIMEOUT, stream=True)

            if response.headers['Content-Type'] == 'text/csv':

                keys = None
                for line in response.iter_lines():
                    line = line.decode('utf-8')
                    if not line:
                        continue
                    if not keys:
                        keys = line.strip().split(',')
                        # Scrub the keys a little.
                        keys = [re.sub('[^a-zA-Z0-9]', '_', k).strip('_').lower()
                                for k in keys]
                        continue

                    item = dict(zip(keys, line.strip().split(',')))
                    if item['longitude'] and item['latitude']:
                        yield item

        except (requests.ConnectionError, requests.ReadTimeout) as e:
            self.logger.exception('Failed to read CSV file at %s', link)
            raise
        except Exception as e:
            self.logger.exception(
                'Unexpected error reading CSV file at %s', link)
        finally:
            if hasattr(response, 'close'):
                response.close()

    def fetch_observations(self):

        login_cookies = self.login()
        projects_data = self.get_projects(login_cookies)

        for csv_link in self.get_csv_links(projects_data):
            yield from self.parse_csv_link(csv_link)

    def get_kml(self, url, params):
        """
        Get kml and return raw contents.
        """
        try:
            response = requests.request(
                "GET", url, headers=None, params=params, verify=False, timeout=DEFAULT_REQUEST_TIMEOUT)
            if response.status_code != 200:
                return None

        except (requests.ConnectTimeout, requests.ReadTimeout) as e:
            logger.exception('Time out for url %s', url)
        else:

            # Assume the data is zipped and otherwise return the content.
            try:
                bf = io.BytesIO(response.content)
                kmz = zipfile.ZipFile(bf, 'r')
                for name in kmz.namelist():
                    kmlbytes = kmz.read(name)
                return kmlbytes
            except:
                return response.content


class SirtrackPlugin(TrackingPlugin):
    '''
    Fetch data from SirTrack API.
    '''
    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=15)

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

                fix_time = _resolve_recorded_at(fix)
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

        recorded_at = _resolve_recorded_at(fix)
        latitude = float(fix['latitude'])
        longitude = float(fix['longitude'])

        side_data = dict((k, fix.get(k))
                         for k in fix.keys() - set(('latitude', 'longitude',)))
        return Obs(source=source, recorded_at=recorded_at, latitude=latitude, longitude=longitude,
                   additional=side_data)


def _resolve_recorded_at(fix):
    return pytz.utc.localize(parse_date('{utc_date} {utc_time}'.format(**fix)))
