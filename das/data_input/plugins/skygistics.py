""" fetch and transform Skygistics (AWT) data into DAS input format
"""
import requests
import xml.etree.ElementTree as etree
from decimal import Decimal
from datetime import datetime, timedelta

from django.utils import timezone
from django.contrib.gis.geos import Point

from observations.models import Observation, Source
from data_input.models import PluginConf, PluginConfSource

from .plugin import DasPlugin, PluginTarget, \
    DasPluginConfigurationError, DasPluginFetchError, \
    DasPluginInsertError, DasPluginTransformationError
from .utils import dictify
import logging

SKYGISTICS_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
SKYGISTICS_PLUGIN_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

SKYGISTICS_API_XMLNS = '{http://www.skygistics.com/SkygisticsAPI}'
SKYGISTICS_API_ENDPOINT = '/SkygisticsAPI/SkygisticsAPI.asmx'
DEFAULT_START_OFFSET = timedelta(days=14)

class SkygisticsLoginError(Exception):
    pass


class SkygisticsClient(object):
    pass


class SkygisticsSatelliteClient(SkygisticsClient):
    def __init__(self, config):
        self.config = config
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
                '{0}{1}/Login'.format(self.config['host'], SKYGISTICS_API_ENDPOINT),
                {
                    'username': self.config['credentials']['username'],
                    'password': self.config['credentials']['password'],
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
            '{0}{1}/GetReplayDataCount'.format(self.config['host'], SKYGISTICS_API_ENDPOINT),
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
            '{0}{1}/GetReplayData'.format(self.config['host'], SKYGISTICS_API_ENDPOINT),
            {
                'imei': imei,
                'startdate': start_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'enddate': end_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'sessionid': self.session_id,
                'skip': skip,
                'limit': limit,
            })
        return etree.fromstring(response_text)

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

        end_date = timezone.now()
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


class SkygisticsSatellitePlugin(DasPlugin):

    def __init__(self, config=None, target=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # config should be a PluginConf object with a jsonb configuration attribute
        if hasattr(config, 'configuration'):

            super().__init__(config=config, target=target)

            # todo:  sanity check config.configuration and extract relevant bits
            client_configuration = self.config.configuration
            self.client = SkygisticsSatelliteClient(client_configuration)
        else:
            raise DasPluginConfigurationError()

    def _fetch(self):
        self.client.begin_session()
        conf_sources = PluginConfSource.objects.filter(plugin_conf=self.config)
        for conf_source in conf_sources:

            try:
                if 'last_fetch' in conf_source.additional:
                    start_date = datetime.strptime(conf_source.additional['last_fetch'], SKYGISTICS_PLUGIN_DATETIME_FORMAT)
                else:

                    start_date = datetime.utcnow() - DEFAULT_START_OFFSET

            except Exception as e:
                self.logger.exception('Failure when getting cursor data for source', conf_source.source_id)

            for unit_info in self.client.fetch_observations(imei=conf_source.source.manufacturer_id,
                                                            start_date=start_date):
                yield (conf_source.source, unit_info)
            # update the conf_source so the time this data was fetched becomes the start for the next batch
            # todo:  this could be set too far in the future ...
            conf_source.additional['last_fetch'] = timezone.now().strftime(SKYGISTICS_PLUGIN_DATETIME_FORMAT)
            conf_source.save()

    def _transform(self, item):
        """
        transform a Skygistics (their xml that hase been dictify'd) data dictionary into a DAS usable dictionary
        :param: item:  a tuple of a Source object and dictionary of Skygistics data
        :return: Source, Observation tuple (similar to param item)
        """
        source, unit_info = item
        observation = {
            'imei': unit_info[('{0}IMEI'.format(SKYGISTICS_API_XMLNS))][0]['_text'],
            'lat': unit_info[('{0}Latitude'.format(SKYGISTICS_API_XMLNS))][0][
                '_text'],
            'lon': unit_info[('{0}Longitude'.format(SKYGISTICS_API_XMLNS))][0][
                '_text'],
            'voltage': unit_info[('{0}Voltage'.format(SKYGISTICS_API_XMLNS))][0][
                '_text'],
            'ts': timezone.make_aware(datetime.strptime(unit_info[('{0}Time'.format(SKYGISTICS_API_XMLNS))][0][
                '_text'], SKYGISTICS_DATETIME_FORMAT), timezone.utc),
            # add T and Z to string timestamp so UTC is obvious.
            'received_time':
                timezone.make_aware(datetime.strptime(unit_info[('{0}ReceivedTime'.format(SKYGISTICS_API_XMLNS))][0][
                    '_text'], SKYGISTICS_DATETIME_FORMAT), timezone.utc).strftime(SKYGISTICS_PLUGIN_DATETIME_FORMAT),
        }
        return source, observation

    def execute(self):
        super().execute()


class SkygisticsTarget(PluginTarget):
    def _handle_item(self, item):
        (source, observation) = item
        if self._pass_filter(observation):
            Observation.objects.add_observation(source, observation)

    def _pass_filter(self, observation):

        try:
            return not (int(float(observation['lon'])) == 180 and int(float(observation['lat'])) == 90)
        except Exception as e:
            self.logger.warn('Failure when filtering skygistics fix.')

        return True # Assume we want to see it