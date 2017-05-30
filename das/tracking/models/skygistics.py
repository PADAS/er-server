import xml.etree.ElementTree as etree
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
import pytz
import copy
from functools import reduce

import requests

from django.utils import timezone
from django.contrib.gis.db import models
from django.contrib.contenttypes.models import ContentType

from tracking.models.plugin_base import Obs, TrackingPlugin, DasPluginFetchError
from tracking.models import SourcePlugin
from observations.models import Source, Subject, SubjectSource

from tracking.models.utils import dictify
import logging

SKYGISTICS_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
SKYGISTICS_PLUGIN_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

SKYGISTICS_API_XMLNS = '{http://www.skygistics.com/SkygisticsAPI}'
SKYGISTICS_API_ENDPOINT = '/SkygisticsAPI/SkygisticsAPI.asmx'


def _qualify(s):
    return '{}{}'.format(SKYGISTICS_API_XMLNS, s)

def _unqualify(s):
    return s.replace(SKYGISTICS_API_XMLNS, '')

class SkygisticsLoginError(Exception):
    pass


class SkygisticsClient(object):
    pass

def str2date(d, default_tzinfo=pytz.UTC):
    '''Parse a date and if it's naive, replace tzinfo with default_tzinfo.'''
    dt = parse_date(d)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tzinfo)
    return dt


# This is a fudge factor for querying Skygistic's API. Dates used for querying will be interpreted as
# Africa/Johannesburg timezone.
SKYGISTICS_SERVICE_TIMEZONE = pytz.timezone('Africa/Johannesburg')


class SkygisticsSatelliteClient(SkygisticsClient):

    def __init__(self, username=None, password=None, service_url='http://skyq1.skygistics.com'):
        self.username = username
        self.password = password
        self.service_url = service_url

        # this is mildly ugly:  skygistics returns '0' for a failed login
        #   but a session_id for success and session_ids may contain hyphens so the session_id must
        #   be a "string"
        self.session_id = '0'
        self.fetch_params = {
            'imei_list': [],
            'start_date': None,
            'end_date': None,
        }
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_text(self, url, query):
        response_text = None
        try:
            response = requests.get(url, query)
            # todo:  sad API, it returns a 500 if any param is bad or missing.
            #   check status code and do better
            if response.status_code != 200:
                raise DasPluginFetchError('Non 200 response.')
            response_text = response.text
        except requests.ConnectionError as e:
            # todo:  handle connection error, etc.
            self.logger.exception('Failed connecting to skygistics API.')
        except requests.Timeout as e:
            # todo:  handle timeout
            self.logger.exception('Time-out connecting to skygistics API.')
        return response_text

    def _login(self):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/Login?username=string&password=string
        sets self.session_id based on LoginResult.  0 for failure

        :param username:
        :param password:
        :return: true for successful login, false otherwise
        """
        try:
            # todo:  the username and password are in the clear here ... !!
            # parse response content for session_id
            self.session_id = etree.fromstring(self._get_text(
                '{0}{1}/Login'.format(self.service_url, SKYGISTICS_API_ENDPOINT),
                {
                    'username': self.username,
                    'password': self.password,
                })).text
        except requests.ConnectionError as e:
            self.logger.exception('Failed connecting, logging in to skygistics API.')
            pass
        except requests.Timeout as e:
            self.logger.exception('Timed-out logging in to skygistics API.')
            pass
        return self.session_id != '0'

    def _get_replay_data_count(self, imei, start_date, end_date):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetReplayDataCount?
            sessionid=string&imei=string&startdate=string&enddate=string

        :param imei:
        :param start_date:
        :param end_date:
        :return:
        """
        if not self.session_id or self.session_id == '0':
            raise SkygisticsLoginError('Client does not have a valid session_id.')
        # todo:  the username and password are in the clear here ...
        response_text = self._get_text(
            '{0}{1}/GetReplayDataCount'.format(self.service_url, SKYGISTICS_API_ENDPOINT),
            {
                'imei': imei,
                'startdate': start_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'enddate': end_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'sessionid': self.session_id,
            })
        try:
            replay_data_count = int(etree.fromstring(response_text).text)
        except TypeError:
            replay_data_count = 0
        return replay_data_count

    def _get_replay_data(self, imei, start_date, end_date, skip, limit):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetReplayData?
            sessionid=string&imei=string&startdate=string&enddate=string&skip=int&limit=int

        :param imei:
        :param start_date:  datetime.date
        :param end_date:  datetime.date
        :param skip:  default=0
        :param limit:  default=100
        :return: replay_data
        """
        if not self.session_id or self.session_id == '0':
            raise SkygisticsLoginError('Client does not have a valid session_id.')
        response_text = self._get_text(
            '{0}{1}/GetReplayData'.format(self.service_url, SKYGISTICS_API_ENDPOINT),
            {
                'imei': imei,
                'startdate': start_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'enddate': end_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'sessionid': self.session_id,
                'skip': skip,
                'limit': limit,
            })
        return etree.fromstring(response_text)

    def _get_unit_list(self):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetUnitList?sessionid=string
        :return:
        """
        if not self.session_id or self.session_id == '0':
            raise SkygisticsLoginError('Client does not have a valid session_id.')
        response_text = self._get_text(
            '{0}{1}/GetUnitList'.format(self.service_url, SKYGISTICS_API_ENDPOINT),
            {
                'sessionid': self.session_id,
            })


        root = etree.fromstring(response_text)

        def _dictify(el, result=None):
            result = result or {}
            for child in el:
                result[_unqualify(child.tag)] = child.text
            return result

        if root.tag == _qualify('ArrayOfUnitInfo'):
            for child in root:
                yield _dictify(child)

    def begin_session(self):
        self._login()

    def fetch_observations(self, imei, start_date, end_date=None):
        """
        Fetch observations from Skygistics for a particular collar based on imei.
        :param imei:
        :param start_date:
        :param end_date:  ignored for now, always current datetime
        :return: generator, yielding individual records.
        """

        # Skygistics service will interpret date query parameters in timezone of server, so we adjust here.
        start_date = start_date.astimezone(SKYGISTICS_SERVICE_TIMEZONE)
        end_date = end_date.astimezone(SKYGISTICS_SERVICE_TIMEZONE)

        # todo: batch calls based on _get_replay_data_count?
        skip = 0
        # if not batching, get total available
        limit = self._get_replay_data_count(
            imei,
            start_date,
            end_date=end_date,
        )

        replay_data_dict = dictify(self._get_replay_data(
            imei,
            start_date,
            end_date=end_date,
            skip=skip,
            limit=limit
        ))
        # if the array is empty (e.g., bad imei) then '{http://www.skygistics.com/SkygisticsAPI}ArrayOfUnitInfo'
        #     will be a dict with a key-value pair '{http://www.w3.org/2001/XMLSchema-instance}nil': 'true'
        if ('{http://www.w3.org/2001/XMLSchema-instance}nil' in replay_data_dict[
            ('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))]
            and replay_data_dict[('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))][
                '{http://www.w3.org/2001/XMLSchema-instance}nil'] == 'true'):
            pass  # todo:  no results!
        else:
            for unit_info in \
                    replay_data_dict[('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))][
                        ('{0}UnitInfo'.format(SKYGISTICS_API_XMLNS))]:
                yield unit_info


class SkygisticsSatellitePlugin(TrackingPlugin):

    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REPORT_INTERVAL = timedelta(hours=1)

    service_username = models.CharField(max_length=50,
                                       help_text='The username for Skygistics API.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for Skygistics API.')
    service_api_url = models.CharField(max_length=50,
                                       help_text='API endpoint for Skygistics service.',
                                       default='http://skyq1.skygistics.com')


    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        client = SkygisticsSatelliteClient(username=self.service_username,
                                           password=self.service_password,
                                           service_url=self.service_api_url)

        client.begin_session()

        try:
            # Given a latest-timestamp, reach back another 12-hours to fill in any gaps.
            st = parse_date(self.cursor_data['latest_timestamp']) - timedelta(hours=12)
        except Exception as e:
            st = datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        end_time = datetime.now(tz=pytz.utc)

        observation = None
        for unit_info in client.fetch_observations(imei=source.manufacturer_id,
                                                   start_date=st,
                                                   end_date=end_time):

            try:
                observation = self._transform(source, unit_info)
                if observation and self._pass_filter(observation):
                    yield observation
            except Exception as e:
                self.logger.exception('processing unit_info.')

        if observation:
            self.cursor_data['latest_timestamp'] = observation.recorded_at.isoformat()

    def _pass_filter(self, observation):
        '''
        Reject fixes that are at 180 x 90.
        :param observation:
        :return: True if the observation passes the filter.
        '''
        try:
            return not (int(observation.longitude) == 180 and int(observation.latitude) == 90)
        except Exception as e:
            self.logger.warn('Failure when filtering skygistics fix.')

        return True


    def _transform(self, source, unit_info):
        """
        transform a Skygistics (their xml that hase been dictify'd) data dictionary into a DAS usable dictionary
        :param: item:  a tuple of a Source object and dictionary of Skygistics data
        :return: Source, Observation tuple (similar to param item)
        """
        try:
            observation = {
                'imei': unit_info[_qualify('IMEI')][0]['_text'],
                'latitude': unit_info[_qualify('Latitude')][0]['_text'],
                'longitude': unit_info[_qualify('Longitude')][0]['_text'],
                'voltage': unit_info[_qualify('Voltage')][0].get('_text'),
                'location': unit_info[_qualify('Location')][0].get('_text'),
                'temperature': unit_info[_qualify('Temperature')][0].get('_text'),
                'recorded_at': timezone.make_aware(datetime.strptime(unit_info[_qualify('Time')][0]['_text'],
                                                                     SKYGISTICS_DATETIME_FORMAT), timezone.utc),
                # add T and Z to string timestamp so UTC is obvious.
                'received_time':
                    timezone.make_aware(datetime.strptime(unit_info[_qualify('ReceivedTime')][0]['_text'],
                                                          SKYGISTICS_DATETIME_FORMAT),
                                        timezone.utc).strftime(SKYGISTICS_PLUGIN_DATETIME_FORMAT),
            }
        except Exception as e:
            self.logger.exception('Transforming skygistics unit_info for source: {}'.format(source.manufacturer_id))
        else:
            return Obs(source=source, recorded_at=observation['recorded_at'],
                                      longitude=float(observation['longitude']), latitude=float(observation['latitude']),
                                      additional=dict((k,observation.get(k)) for k in ('imei', 'voltage', 'received_at', 'temperature', 'location')))


    def _maintenance(self):
        self._sync_unit_info()

    def _sync_unit_info(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        client = SkygisticsSatelliteClient(username=self.service_username,
                                           password=self.service_password,
                                           service_url=self.service_api_url)

        client.begin_session()

        try:

            unitlist = client._get_unit_list()

            for unit in unitlist:

                src = ensure_source('tracking-device', unit['IMEI'])
                ensure_source_plugin(src, self)
                ts = str2date(unit['Time'])
                ensure_subject_source(src, ts, unit['Name'])
        except Exception as e:
            self.logger.exception('Error in maintenance')



# Helper functions for hydrating Source and Subject for the given message.
def ensure_source(source_type, manufacturer_id):
    src, created = Source.objects.get_or_create(source_type=source_type,
                                   manufacturer_id=manufacturer_id,
                                   defaults={'model_name':'skygistics',
                                             'additional': {'note': 'Created automatically during feed sync.'}})

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

        subject_name = subject_name or 'sky-{}'.format(source.manufacturer_id)

        sub, created = Subject.objects.get_or_create(
            subject_type='wildlife', subject_subtype='elephant',
            name=subject_name,
            defaults=dict(additional=dict(region='', country='', ))
        )

        d1 = event_time - timedelta(days=30)
        d2 = d1 + timedelta(days=5*365)
        if sub:
            subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                 defaults=dict(assigned_range=(d1, d2), additional={
                                                                     'note': 'Created automatically during feed sync.'}))

    return subject_source

