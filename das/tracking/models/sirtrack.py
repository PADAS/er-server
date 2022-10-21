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
from django.contrib.contenttypes.fields import GenericRelation

from tracking.models.plugin_base import Obs, TrackingPlugin, DasDefaultTarget, SourcePlugin
from tracking.pubsub_registry import notify_new_tracks

from tracking.models.utils import split_link, parse_cookie
from observations.models import Source

logger = logging.getLogger(__name__)

# SirTrack server may be a little slow, so using a long timeout for first byte.
DEFAULT_REQUEST_TIMEOUT = (3, 30)  # seconds for (connect, read)
CSV_REQUEST_TIMEOUT = (3, 30)  # seconds


class SirTrackClient(object):
    def __init__(self, service_api=None, username=None, password=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.username = username
        self.password = password
        self.service_api = service_api

    def login(self):
        service_root = f'{self.service_api}/json-rpc/'
        login_data = {'id': 2,
                      'method': 'loginFrontService.login',
                      'params': [self.username, self.password]
                      }

        try:
            result = requests.post(
                service_root, json=login_data, timeout=DEFAULT_REQUEST_TIMEOUT)
        except (requests.ConnectionError, requests.ReadTimeout):
            self.logger.exception(
                'Failed to log in to SirTrack API. Service username=%s', self.username)
        else:
            if result.status_code == 200:
                cookies = parse_cookie(result.headers['Set-Cookie'])
                return cookies
            else:
                self.logger.error('Unable to log in to Sirtrack. result.code: %s, result.data: %s',
                                  result.status_code, result.data)

    def get_projects(self, cookies):

        vosao_session_value = cookies.get('vosao_session')
        cookie_val = '='.join(('vosao_session', vosao_session_value))

        try:
            call_timestamp = int(time.time() * 1000)
            result = requests.get(f'{self.service_api}/restlet/projects?_={call_timestamp}',
                                  headers=dict(cookie=cookie_val), timeout=DEFAULT_REQUEST_TIMEOUT)
        except Exception as exc:
            self.logger.exception('Unable to download Sirtrack Project.')
        else:
            if result.status_code == 200:
                return json.loads(result.text)

        return None

    def get_csv_links(self, projects_data):
        # Fetch the top-level KML document from Sirtrack and use its NetworkLinks to download
        # CSV files of track data.

        if not projects_data:
            self.logger.warning('Sirtrack project data is empty.')
            return

        for pd in projects_data:
            kml_url = '{service_api}/restlet/geo/{id}/{name}.kmz'.format(
                service_api=self.service_api, **pd)

            self.logger.info('Download Sirtrack data: %s', kml_url)
            kmldata = self.get_kml(kml_url, params=dict(key=pd['geoJsonKey']))

            if not kmldata:
                self.logger.error('Failed to download KML at %s', kml_url)

            k = fastkml.kml.KML()
            k.from_string(kmldata)

            for f in k.features():
                if hasattr(f, 'link'):
                    csv_link = f.link.replace('.kmz', '.csv').replace(' ', '+')
                    self.logger.debug('Found Sirtrack link: %s', csv_link)
                    yield csv_link

    def get_csv_dataset(self, link):
        '''
        Yield lines from the link if it is CSV content.

        Handle decoding the data, timeouts and stream lifecycle.
        '''

        response = None
        try:
            response = requests.get(
                link, timeout=CSV_REQUEST_TIMEOUT, stream=True)
            if response.headers['Content-Type'] == 'text/csv':

                for line in response.iter_lines():
                    record = line.decode('utf-8')
                    if not record:
                        continue
                    yield record

        except (requests.ConnectionError, requests.ReadTimeout) as e:
            self.logger.warning(
                'Failed to read CSV file at %s, ex=%s', link, e)
            raise
        except Exception as e:
            self.logger.exception(
                'Unexpected error reading CSV file at %s', link)
        finally:
            if hasattr(response, 'close'):
                response.close()

    def parse_csv_link(self, link):
        '''
        Read chunked response as a CSV file and yield a dictionary for each row.
        :param link: A link to a CSV file.
        :return: generate records as dicts, using CSV headers as keys.
        '''

        self.logger.info('Parsing CSV link: %s', link)

        keys = None
        for line in self.get_csv_dataset(link):

            # guard for blank lines.
            if not line:
                continue

            # Assume first non-blank line is header.
            if not keys:
                keys = line.strip().split(',')
                # Scrub the keys a little.
                keys = [re.sub('[^a-zA-Z0-9]', '_', k).strip('_').lower()
                        for k in keys]
                continue

            item = dict(zip(keys, line.strip().split(',')))

            if item['longitude'] and item['latitude']:
                yield item

    def fetch_observations(self):

        login_cookies = self.login()

        if not login_cookies:
            self.logger.warning('Failed to login to Sirtrack API.')

        projects_data = self.get_projects(login_cookies)

        if not projects_data:
            self.logger.warning('Project data is empty.')
            return

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
            self.logger.warning('Failed to read KML file at %s, ex=%s', url, e)
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
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)

    service_username = models.CharField(max_length=50,
                                        help_text='The username for querying the SirTrack service.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for querying the SirTrack service.')
    service_api = models.CharField(max_length=50,
                                   help_text='The API endpoint for SirTrack data.',
                                   default='https://data.sirtrack.com')

    DEFAULT_SUBJECT_SUBTYPE = 'cheetah'
    DEFAULT_SOURCE_TYPE = 'tracking-device'
    DEFAULT_MODEL_NAME = 'Lotek'
    READ_OVERLAP = timedelta(hours=24)

    source_plugin_reverse_relation = 'sirtrackplugin'
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

        # If these are indicated in the 'additional' blob, the use them.
        defaults = self.additional.get('defaults', {})

        # Support legacy key 'subject_subtype')
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
        read_start_limit = st - self.READ_OVERLAP
        for fix in client.fetch_observations():
            try:

                fix_time = _resolve_recorded_at(fix)
                if fix_time < read_start_limit:
                    continue

                if self._pass_filter(fix):

                    manufacturer_id = fix['tag_id']
                    if manufacturer_id in source_map:
                        source = source_map.get(manufacturer_id)
                    else:
                        source = Source.objects.ensure_source(source_type=default_source_type,
                                                              provider=self.provider.provider_key,
                                                              manufacturer_id=manufacturer_id,
                                                              model_name=default_model_name,
                                                              subject={
                                                                  'subject_subtype_id': default_subject_subtype,
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
                self.logger.error('processing SirTrack. Ex=%s', e)

        if lt:  # Update cursor data.
            self.additional['latest_timestamp'] = lt.isoformat()

    def _pass_filter(self, fix):
        return True

    def _transform(self, fix, source):

        try:
            recorded_at = _resolve_recorded_at(fix)
            latitude = float(fix['latitude'])
            longitude = float(fix['longitude'])
        except:
            self.logger.warning(
                'Failed to transform fix, so ignoring it: %s', fix)
            return None

        side_data = dict((k, fix.get(k))
                         for k in fix.keys() - set(('latitude', 'longitude',)))
        return Obs(source=source, recorded_at=recorded_at, latitude=latitude, longitude=longitude,
                   additional=side_data)


def _resolve_recorded_at(fix):
    return pytz.utc.localize(parse_date('{utc_date} {utc_time}'.format(**fix)))
