""" fetch and transform Skygistics (AWT) data into DAS input format
"""
import xml.etree.ElementTree as etree
import requests

from  data_input.plugins.utils import dictify


class SkygisticsLoginError(Exception):
    pass


class SkygisticsSatelliteClient:
    def __init__(self):
        # this is mildly ugly:  skygistics returns '0' for a failed login
        #   but a session_id for success and session_ids may contain hyphens so the session_id must
        #   be a "string"
        self.session_id = '0'
        # todo:  relocate?
        self.host = 'http://skyq1.skygistics.com'
        self.api = '/SkygisticsAPI/SkygisticsAPI.asmx'

    def login(self, username, password):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/Login?username=string&password=string
        sets self.session_id based on LoginResult.  0 for failure

        :param username:
        :param password:
        :return: true for successful login, false otherwise
        """
        try:
            # todo:  the username and password are in the clear here ...
            response = requests.get('{0}{1}/Login'.format(self.host, self.api),
                                    {
                                        'username': username,
                                        'password': password
                                    })
            # parse response content for session_id
            self.session_id = etree.fromstring(response.text).text
        except requests.ConnectionError as e:
            # todo:  handle connection error, etc.
            pass
        except requests.Timeout as e:
            # todo:  handle timeout
            pass
        return self.session_id != '0'

    def get_replay_data_count(self, imei, start_date, end_date):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetReplayDataCount?
            sessionid=string&imei=string&startdate=string&enddate=string

        :param imei:
        :param start_date:
        :param end_date:
        :return:
        """
        if self.session_id == '0':
            raise SkygisticsLoginError('Client does not have a valid session_id.')
        try:
            # todo:  the username and password are in the clear here ...
            response = requests.get('{0}{1}/GetReplayDataCount'.format(self.host, self.api),
                                    {
                                        'imei': imei,
                                        'startdate': start_date,
                                        'enddate': end_date,
                                        'sessionid': self.session_id
                                    })
            # todo:  sad API, it returns a 500 if any param is bad or missing.
            #   check status code and do better.
            if response.status_code != 200:
                raise SkygisticsLoginError('Non 200 response.')

            # parse response content for session_id
            replay_data_count = etree.fromstring(response.text).text
        except requests.ConnectionError as e:
            # todo:  handle connection error, etc.
            pass
        except requests.Timeout as e:
            # todo:  handle timeout
            pass
        # todo:  finish this return
        return False

    def get_replay_data(self, imei, start_date, end_date, skip, limit):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetReplayData?
            sessionid=string&imei=string&startdate=string&enddate=string&skip=int&limit=int

        :param imei:
        :param start_date:
        :param end_date:
        :return: replay_data
        """
        replay_data_list = []
        if self.session_id == '0':
            raise SkygisticsLoginError('Client does not have a valid session_id.')
        try:
            # todo:  the username and password are in the clear here ...
            response = requests.get('{0}{1}/GetReplayData'.format(self.host, self.api),
                                    {
                                        'imei': imei,
                                        'startdate': start_date,
                                        'enddate': end_date,
                                        'sessionid': self.session_id,
                                        'skip': skip,
                                        'limit': limit
                                    })
            # todo:  sad API, it returns a 500 if any param is bad or missing.
            #   check status code and do better.
            if response.status_code != 200:
                raise SkygisticsLoginError('Non 200 response.')

            # parse response content for session_id
            replay_data = etree.fromstring(response.text)

            # note:  Jake's been wondering if the fix time is local rather than UTC ...
            # todo:  we can probably forgo this or extend dictify to take a key mapping that we pass in
            replay_data_dict = dictify(replay_data)

            for unit_info in replay_data_dict['{http://www.skygistics.com/SkygisticsAPI}ArrayOfUnitInfo'][
                    '{http://www.skygistics.com/SkygisticsAPI}UnitInfo']:
                # todo: key map? ...
                replay_data_list.append(
                    {
                        'imei': unit_info['{http://www.skygistics.com/SkygisticsAPI}IMEI'][0]['_text'],
                        'lat': unit_info['{http://www.skygistics.com/SkygisticsAPI}Latitude'][0]['_text'],
                        'long': unit_info['{http://www.skygistics.com/SkygisticsAPI}Longitude'][0]['_text'],
                        'voltage': unit_info['{http://www.skygistics.com/SkygisticsAPI}Voltage'][0]['_text'],
                        'fix_time': unit_info['{http://www.skygistics.com/SkygisticsAPI}Time'][0]['_text'],
                        'received_time': unit_info['{http://www.skygistics.com/SkygisticsAPI}ReceivedTime'][0]['_text'],
                    })

        except requests.ConnectionError as e:
            # todo:  handle connection error, etc.
            pass
        except requests.Timeout as e:
            # todo:  handle timeout
            pass
        # todo:  finish this return
        return replay_data_list
