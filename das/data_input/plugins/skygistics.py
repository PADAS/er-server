""" fetch and transform Skygistics (AWT) data into DAS input format
"""
import xml.etree.ElementTree as etree
import requests
from data_input.models import PluginConf
from .plugin import DasPlugin, PluginTarget, \
    DasPluginConfigurationError, DasPluginFetchError, \
    DasPluginInsertError, DasPluginTransformationError
from .utils import dictify

SKYGISTICS_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

SKYGISTICS_API_XMLNS = '{http://www.skygistics.com/SkygisticsAPI}'
SKYGISTICS_API_ENDPOINT = '/SkygisticsAPI/SkygisticsAPI.asmx'


class SkygisticsLoginError(Exception):
    pass


class SkygisticsSatelliteClient(object):
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
            pass
        except requests.Timeout as e:
            # todo:  handle timeout
            pass
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
            # todo:  handle connection error, etc.
            pass
        except requests.Timeout as e:
            # todo:  handle timeout
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
        # parse response content for session_id
        replay_data_count = etree.fromstring(response_text).text
        return False

    def _get_replay_data(self, imei, start_date, end_date, skip, limit):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetReplayData?
            sessionid=string&imei=string&startdate=string&enddate=string&skip=int&limit=int

        :param imei:
        :param start_date:
        :param end_date:
        :param skip:
        :param limit:
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
        # parse response content for session_id
        self.fetch_data = etree.fromstring(response_text)

    def begin_session(self):
        self._login()

    def fetch_observations(self, imei, start_time, end_time=None):
        """
        Fetch observations from Skygistics for a particular collar based on imei.
        :param imei:
        :param start_time:
        :param end_time:
        :return: generator, yielding individual records.
        """

        self._get_replay_data(
            imei,
            start_time,
            end_time,  # todo: get latest
            skip=0,
            limit=100  # todo: batch based on _get_replay_data_count
        )
        # todo:  perhaps we can forgo this or extend dictify to accept a key mapping?
        replay_data_dict = dictify(self.fetch_data)
        for unit_info in \
                replay_data_dict[('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))][
                    ('{0}UnitInfo'.format(SKYGISTICS_API_XMLNS))]:
            yield {
                'imei': unit_info[('{0}IMEI'.format(SKYGISTICS_API_XMLNS))][0]['_text'],
                'lat': unit_info[('{0}Latitude'.format(SKYGISTICS_API_XMLNS))][0][
                    '_text'],
                'long': unit_info[('{0}Longitude'.format(SKYGISTICS_API_XMLNS))][0][
                    '_text'],
                'voltage': unit_info[('{0}Voltage'.format(SKYGISTICS_API_XMLNS))][0][
                    '_text'],
                'fix_time': unit_info[('{0}Time'.format(SKYGISTICS_API_XMLNS))][0][
                    '_text'],
                'received_time':
                    unit_info[('{0}ReceivedTime'.format(SKYGISTICS_API_XMLNS))][0][
                        '_text'],
            }


class SkygisticsSatelliteTransformer(object):
    def __init__(self):
        pass

    def _transform(self):
        pass


class SkygisticsSatellitePlugin(DasPlugin):
    def __init__(self, config, target):
        # config should be a PluginConf object with a jsonb configuration attribute
        if isinstance(config, PluginConf):
            self.config = config

            # todo:  sanity check config.configuration and extract relevant bits
            client_configuration = self.config.configuration
            self.client = SkygisticsSatelliteClient(client_configuration)

            self.transformer = SkygisticsSatelliteTransformer()
            super().__init__(self.config, target)
        else:
            raise DasPluginConfigurationError()

    def _fetch(self, *args, **kwargs):

        self.client.begin_session()
        for source in self.config.config_sources:
            yield from self.client.fetch_observations(source.manufacturer_id, start_time=start_time)

    def _insert(self, item, *args, **kwargs):
        super()._insert(item)

    def execute(self):
        pass
