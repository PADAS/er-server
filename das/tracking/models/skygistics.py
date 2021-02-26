from datetime import datetime, timedelta, time
import pickle
import copy
import urllib.parse
import io
import zipfile
import base64
from typing import NamedTuple, Iterator, Type

import xml.etree.ElementTree as etree
from dateutil.parser import parse as parse_date
import pytz
import requests
from django.utils import timezone
from django.contrib.gis.db import models
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.contrib.contenttypes.fields import GenericRelation

from tracking.models.plugin_base import Obs, TrackingPlugin, DasPluginFetchError, SourcePlugin
from tracking.models import SourcePlugin
from observations.models import Source, Subject, SubjectSource

from tracking.models.utils import dictify
import logging
from .utils import to_float


SKYGISTICS_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
SKYGISTICS_PLUGIN_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'


SKYGISTICS_API_XMLNS = '{http://www.skygistics.com/SkygisticsAPI}'
SKYGISTICS_API_ENDPOINT = '/SkygisticsAPI/SkygisticsAPI.asmx'

SKYGISTICS_DEFAULT_UNIT_DATETIME = datetime(
    year=1970, month=1, day=1, tzinfo=pytz.UTC)


def _qualify(s):
    return '{}{}'.format(SKYGISTICS_API_XMLNS, s)


def _unqualify(s):
    return s.replace(SKYGISTICS_API_XMLNS, '')


class SkygisticsLoginError(Exception):
    pass


class SkygisticsClient:
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

    def fetch_observations(self, imei, start_date, end_date=None):
        raise NotImplementedError()

    def begin_session(self):
        raise NotImplementedError()

    def get_unit_list(self):
        raise NotImplementedError()


def str2date(d, default_tzinfo=pytz.UTC):
    '''Parse a date and if it's naive, replace tzinfo with default_tzinfo.'''
    dt = parse_date(d)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tzinfo)
    return dt


# This is a fudge factor for querying Skygistic's API. Dates used for querying will be interpreted as
# Africa/Johannesburg timezone.
SKYGISTICS_SERVICE_TIMEZONE = pytz.timezone('Africa/Johannesburg')


def get_client(username=None, password=None, service_url=None):
    sq_class = SkygisticsQ1Client
    if service_url and 'skyq3' in service_url:
        sq_class = SkygisticsQ3Client
    return sq_class(username=username, password=password,
                    service_url=service_url)


class Company(NamedTuple):
    rights: str
    company_type: int
    admin_pwd: str
    user_name: str
    company_id: int


class Unit(NamedTuple):
    name: str
    time: datetime
    status: str
    status_code: int
    speed: float
    voltage: float
    temperature: float
    user: str
    mobid: str
    longitude: float
    latitude: float
    lmtime: datetime
    imei: str
    regno: str


class Replay(NamedTuple):
    time: datetime
    status: str
    speed: float
    voltage: float
    temperature: float
    longitude: float
    latitude: float
    place: str
    location: str
    bearing: float
    status_flags: str
    altitude: str
    red: str
    green: str
    blue: str
    is_event: str
    lmtime: datetime
    commodity: str
    description: str
    odometer: str
    cum_hours: str


class RPoint(NamedTuple):
    longitude: float
    latitude: float


class ReplayResult(NamedTuple):
    count: int


class Observation(NamedTuple):
    imei: str
    latitude: float
    longitude: float
    voltage: float
    location: str
    temperature: float
    recorded_at: datetime
    received_time: datetime


class Fault(NamedTuple):
    code: str
    message: str
    detail: str


class SkygisticsQ3Client(SkygisticsClient):
    """
    See TrackingAPI.cs for more details

    This API allows us to specify the timezone, therefore we won't have to deal
    with offsets as seen in the Q1 api

    """
    default_url = 'http://skyq3.skygistics.com'
    server_path = '/TrackingAPI.asmx'
    xml_envelope = '''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <{action_tag} xmlns="http://tempuri.org/">
      {body}
    </{action_tag}>
  </soap:Body>
</soap:Envelope>
'''
    namespaces = {'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                  'b': 'http://tempuri.org/'}
    encode_filename = 'ZippedFile'
    time_zone = '0'  # GMT
    company = None
    user_agent = 'Mozilla/4.0 (compatible; MSIE 6.0; MS Web Services Client Protocol 4.0.30319.42000)'
    replay_page_limit = 100

    def __init__(self, username=None, password=None, service_url=None):
        if not service_url:
            service_url = self.default_url

        super().__init__(username=username, password=password, service_url=service_url)

    def _is_logged_in(self):
        if self.company and self.company.company_id:
            return True

    def _parse_company_from_result(self, result):
        result_array = result.split('[')
        details = result_array[0].split(',')

        #found in login.cs-showmainwindow
        if len(details) != 7:
            raise ValueError('Invalid company result from login')

        company = Company(
            rights=result_array[1],
            company_type=int(details[0]),
            admin_pwd=details[1],
            user_name=details[3],
            company_id=int(details[5])
        )

        return company

    def _parse_unitlist_from_result(self, result):
        # MobileListViewModel
        strArray1 = result.split('~')
        for index1 in range(0, len(strArray1)):
            strArray2 = strArray1[index1].split('`')

            try:
                imei = strArray2[18]
                name = strArray2[0]
                time = str2date(strArray2[1]) if strArray2[1] else None
                status = strArray2[2]
                mobid = strArray2[11]
                status_code = int(strArray2[24]) if len(
                    strArray2[24]) > 0 else 0
                if time is not None:
                    unit = Unit(
                        name=name,
                        time=time,
                        status=status,
                        mobid=mobid,
                        speed=round(float(strArray2[3])),
                        voltage=to_float(strArray2[4]),
                        temperature=to_float(strArray2[5]),
                        user=strArray2[7],
                        longitude=strArray2[12],
                        latitude=strArray2[13],
                        lmtime=datetime.utcfromtimestamp(int(strArray2[15])),
                        imei=imei,
                        regno=strArray2[26],
                        status_code=status_code
                    )
                else:
                    unit = Unit(name=name, time=time, status=status, imei=imei,
                                mobid=mobid, longitude=None, latitude=None, lmtime=None,
                                regno=None,
                                speed=None, voltage=0, temperature=0,
                                user=None,
                                status_code=status_code)
            except ValueError:
                self.logger.info(
                    'Invalid unit info for {imei}, data={data}'.format(
                        imei=imei,
                        data=strArray2
                    ))
                continue

            yield unit

    def _parse_replay_data_from_result(self, result):
        points = []
        str1 = result
        if not str1:
            return

        strArray1 = str1.split('$')
        if len(strArray1) < 3 or strArray1 == 'REPLAYEND':
            return

        str2 = strArray1[2]
        if 'REPLAYDATA' not in str2:
            return

        total_records = int(strArray1[0])
        yield ReplayResult(count=total_records)

        fetched_record_count = 0
        strArray2 = str2.split(',')
        for index1 in range(1, len(strArray2)):
            fetched_record_count += 1
            strArray3 = strArray2[index1].split('^')
            strArray4 = strArray3[15].split(';')
            location = ' '
            place = None
            if len(strArray4) > 1:
                place = strArray4[0]
                location = ' '
                for index2 in range(1, len(strArray4)):
                    location = location + strArray4[index2] + ';'
            elif len(strArray4) == 1:
                place = strArray4[0]
                location = ' '
            else:
                place = strArray3[15]
                location = strArray3[15]

            replay = Replay(
                time=str2date(strArray3[0]),
                status=strArray3[1],
                speed=round(float(strArray3[2]), 1),
                voltage=to_float(strArray3[3]),
                temperature=to_float(strArray3[4]),
                longitude=float(strArray3[5]),
                latitude=float(strArray3[6]),
                place=place,
                location=location,
                bearing=float(strArray3[7]),
                status_flags=strArray3[8],
                altitude=strArray3[9],
                red=strArray3[10],
                green=strArray3[11],
                blue=strArray3[12],
                is_event=strArray3[13],
                lmtime=datetime.utcfromtimestamp(int(strArray3[14])),
                commodity=strArray3[16],
                description=strArray3[17],
                odometer=strArray3[20],
                cum_hours=strArray3[21]
            )

            minx = 180.0
            maxx = -180.0
            miny = 90.0
            maxy = -90.0

            x = float(strArray3[5])
            y = float(strArray3[6])
            if x != 0.0:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
            if y != 0.0:
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y

            points.append(RPoint(x, y))
            yield replay

    def decode_field(self, field):
        if not field:
            return None
        memory_zip = zipfile.ZipFile(io.BytesIO(base64.b64decode(field)))
        decoded_data = memory_zip.read(self.encode_filename)
        decoded_data = decoded_data.decode('utf-8')
        return decoded_data

    def encode_field(self, field):
        memory_file = io.BytesIO()
        memory_zip = zipfile.ZipFile(
            memory_file, "w", zipfile.ZIP_DEFLATED, False)
        memory_zip.writestr(self.encode_filename, field)
        memory_zip.close()
        memory_file.seek(0)
        encoded_data = base64.b64encode(memory_file.read())
        encoded_data = encoded_data.decode('utf-8')
        return encoded_data

    def get_action_result_from_response_body(self, result_tag, response_body):
        root = etree.fromstring(response_body)

        action_element = root.find('.//b:{result_tag}'.format(result_tag=result_tag),
                                   namespaces=self.namespaces)
        if action_element is None:
            action_element = root.find('.//{result_tag}'.format(result_tag=result_tag),
                                       namespaces=self.namespaces)
        return action_element.text

    def _get_fault(self, response_body):
        fault_code_tag = 'faultcode'
        fault_tag = 'faultstring'
        detail_tag = 'detail'
        fault_code = self.decode_field(
            self.get_action_result_from_response_body(fault_code_tag, response_body))
        fault = self.decode_field(
            self.get_action_result_from_response_body(fault_tag, response_body))
        detail = ''
        if detail_tag in response_body:
            detail = self.decode_field(
                self.get_action_result_from_response_body(detail_tag, response_body))
        return Fault(fault_code, fault, detail)

    def make_soap_call(self, action, action_tag, body):
        headers = {'content-type': 'text/xml',
                   'soapaction': '"{0}"'.format(action),
                   'user-agent': self.user_agent,
                   }
        envelope = self.xml_envelope.format(body=body, action=action,
                                            action_tag=action_tag)
        url = urllib.parse.urljoin(self.service_url, self.server_path)

        try:
            response = requests.post(
                url, data=envelope, headers=headers, timeout=(30, 60))
            if response.status_code != 200:
                fault = self._get_fault(response.text)
                raise DasPluginFetchError('{code} response for url {url}, {fault}'.format(
                    code=response.status_code, url=url, fault=fault))

            return response.text

        except requests.ConnectionError as e:
            # todo:  handle connection error, etc.
            self.logger.exception('Failed connecting to skygistics API.')
            raise
        except requests.Timeout as e:
            # todo:  handle timeout
            self.logger.exception('Time-out connecting to skygistics API.')
            raise
        return

    def get_company_list(self):
        """
        list of users in the company
        arg = company id (for example 2586)

        result =
        """
        action = 'http://tempuri.org/GetCompanyNumbers'
        action_tag = 'GetCompanyNumbers'
        result_tag = 'GetCompanyNumbersResult'
        raise NotImplementedError()

    def login(self):
        """
        user =
        password =
        tz = utcoffset.TotalSeconds
        set companyid from here.
        """
        action = 'http://tempuri.org/login'
        action_tag = 'login'
        result_tag = 'loginResult'

        body_template = '''<user>{user}</user>
                  <pwd>{pwd}</pwd>
                  <tz>{tz}</tz>'''

        body = body_template.format(
            user=self.encode_field(self.username),
            pwd=self.encode_field(self.password),
            tz=self.encode_field(self.time_zone)
        )

        response_body = self.make_soap_call(action, action_tag, body)

        result = self.decode_field(
            self.get_action_result_from_response_body(result_tag, response_body))

        if result_tag == 'KO':
            raise SkygisticsLoginError('Invalid username or password')

        self.company = self._parse_company_from_result(result)
        return self.company

    def _get_replay_data(self, unit, start_date, end_date, skip=0, limit=100):
        """
        start and end are iso formatted
        mobid is a number (not imei)
        tz is timezone for example -25200 (gonarezhou)
        company is a number 2586 (gonarezhou)
        offset(skip) number of records to skip, 0 for instance
        limit number of records to return, 20000 for example
        proc string, for example 'trips'
        :return:
        """
        action = 'http://tempuri.org/getReplayData'
        action_tag = 'getReplayData'
        result_tag = 'getReplayDataResult'

        body_template = '''<mobid>{mobid}</mobid>
                  <from>{start}</from>
                  <to>{end}</to>
                  <timez>{tz}</timez>
                  <company>{company}</company>
                  <offset>{skip}</offset>
                  <limit>{limit}</limit>
                  <proc>{proc}</proc>'''

        company = '-' + str(self.company.company_id)
        skip = 0
        limit = 100

        params = dict(mobid=self.encode_field(unit.mobid),
                      start=self.encode_field(start_date.isoformat()),
                      end=self.encode_field(end_date.isoformat()),
                      tz=self.encode_field(self.time_zone),
                      company=self.encode_field(company),
                      skip=self.encode_field(str(skip)),
                      limit=self.encode_field(str(limit)),
                      proc=self.encode_field('')
                      )
        body = body_template.format(**params)
        response_body = self.make_soap_call(action, action_tag, body)
        result = self.decode_field(
            self.get_action_result_from_response_body(result_tag,
                                                      response_body))
        return result

    def _transform_to_observation(self, imei, replay):
        return Observation(
            imei=imei,
            latitude=replay.latitude,
            longitude=replay.longitude,
            voltage=replay.voltage,
            location=replay.location,
            temperature=replay.temperature,
            recorded_at=replay.time,
            received_time=None,
        )

    def get_replay_data(self, mobid, start_date, end_date):
        offset = 0
        total_records = 0
        fetched_records = 0

        while True:
            result = self._get_replay_data(
                mobid, start_date, end_date,
                offset, self.replay_page_limit)

            for replay in self._parse_replay_data_from_result(result):
                if isinstance(replay, ReplayResult):
                    total_records = replay.count
                    continue
                fetched_records += 1
                yield replay
            if fetched_records >= total_records:
                break
            offset += self.replay_page_limit

    def get_replay_data_count(self, mobid, start_date, end_date):
        result = self._get_replay_data(
            mobid, start_date, end_date,
            0, 1)

        replay_result = next(self._parse_replay_data_from_result(result))

        return replay_result.count

    def get_unit_list(self, lmtime='0'):
        timeout = 600  # seconds
        version = 1
        key = '{classname}-get_unit_list-{lmtime}-{company}-{username}'.format(
            classname=self.__class__.__name__,
            lmtime=str(lmtime), company=str(self.company.company_id),
            username=self.username)

        unit_list = None
        unit_list_raw = cache.get(key, version=version)
        if unit_list_raw:
            unit_list = pickle.loads(unit_list_raw)
        if not unit_list or not isinstance(unit_list, list):
            unit_list = self._uncached_get_unit_list(lmtime=lmtime)
            cache.set(key, pickle.dumps(unit_list), timeout)
        return unit_list

    def _uncached_get_unit_list(self, lmtime):
        """
        company
        timezone
        lmtime ? '1523232586', use '0' to get all
        """
        action = 'http://tempuri.org/getUnitList'
        action_tag = 'getUnitList'
        result_tag = 'getUnitListResult'
        body_template = '''<company>{company}</company>
                <tz>{tz}</tz>
                <lmtime>{lmtime}</lmtime>
               '''
        body = body_template.format(tz=self.encode_field(self.time_zone),
                                    company=self.encode_field(
                                        str(self.company.company_id)),
                                    lmtime=self.encode_field(lmtime))
        response_body = self.make_soap_call(action, action_tag, body)
        result = self.get_action_result_from_response_body(
            result_tag, response_body)
        result = self.decode_field(result)
        units = list(self._parse_unitlist_from_result(result))
        return units

    def begin_session(self):
        self.login()

    def is_unit_active(self, unit):
        return unit.status_code > 0

    def fetch_observations(self, imei, start_date, end_date=None):
        for unit in self.get_unit_list():
            if unit.imei == imei:
                if not self.is_unit_active(unit):
                    self.logger('Unit {imei} is not active, status_code {status_code}'.format(
                        imei=unit.imei, status_code=unit.status_code))
                    return

                for replay in self.get_replay_data(unit,
                                                   start_date=start_date,
                                                   end_date=end_date):
                    yield self._transform_to_observation(imei, replay)

                return

        raise KeyError('IMEI {imei} not found'.format(imei=imei))


class SkygisticsQ1Client(SkygisticsClient):
    def _get_text(self, url, query):
        response_text = None
        try:
            response = requests.get(url, query, timeout=5.0)
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
            response = self._get_text(
                '{0}{1}/Login'.format(self.service_url,
                                      SKYGISTICS_API_ENDPOINT),
                {
                    'username': self.username,
                    'password': self.password,
                })
            self.session_id = etree.fromstring(response).text
        except requests.ConnectionError as e:
            self.logger.exception(
                'Failed connecting, logging in to skygistics API.')
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
            raise SkygisticsLoginError(
                'Client does not have a valid session_id.')
        # todo:  the username and password are in the clear here ...
        response_text = self._get_text(
            '{0}{1}/GetReplayDataCount'.format(self.service_url,
                                               SKYGISTICS_API_ENDPOINT),
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
            raise SkygisticsLoginError(
                'Client does not have a valid session_id.')
        response_text = self._get_text(
            '{0}{1}/GetReplayData'.format(self.service_url,
                                          SKYGISTICS_API_ENDPOINT),
            {
                'imei': imei,
                'startdate': start_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'enddate': end_date.strftime(SKYGISTICS_DATETIME_FORMAT),
                'sessionid': self.session_id,
                'skip': skip,
                'limit': limit,
            })
        return etree.fromstring(response_text)

    def get_unit_list(self):
        """
        GET /SkygisticsAPI/SkygisticsAPI.asmx/GetUnitList?sessionid=string
        :return:
        """
        if not self.session_id or self.session_id == '0':
            raise SkygisticsLoginError(
                'Client does not have a valid session_id.')
        response_text = self._get_text(
            '{0}{1}/GetUnitList'.format(self.service_url,
                                        SKYGISTICS_API_ENDPOINT),
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
                unit = _dictify(child)
                yield Unit(
                    imei=unit['IMEI'],
                    name=unit['Name'],
                    longitude=float(unit['Longitude']),
                    latitude=float(unit['Latitude']),
                    status=unit['Status'],
                    time=str2date(unit['Time']) if unit['Time'] else None,
                    speed=float(unit['Speed']),
                    regno=None,
                    mobid=None,
                    lmtime=None,
                    temperature=unit['Temperature'],
                    voltage=int(unit['Voltage']),
                    user=None

                )

    def begin_session(self):
        if not self._login():
            raise DasPluginFetchError('Failed to login')

    def _transform_to_observation(self, unit_info):
        """
        transform a Skygistics (their xml that has been dictify'd) data dictionary into an Observation
        :param: item:  a tuple of a Source object and dictionary of Skygistics data
        :return: Observation tuple (similar to param item)
        """
        try:
            observation = Observation(
                imei=unit_info[_qualify('IMEI')][0]['_text'],
                latitude=float(unit_info[_qualify('Latitude')][0]['_text']),
                longitude=float(unit_info[_qualify('Longitude')][0]['_text']),
                voltage=to_float(unit_info[_qualify('Voltage')][0].get('_text')),
                location=unit_info[_qualify('Location')][0].get('_text'),
                temperature=to_float(unit_info[_qualify('Temperature')][0].get('_text')),
                recorded_at=timezone.make_aware(datetime.strptime(unit_info[_qualify('Time')][0]['_text'],
                                                                  SKYGISTICS_DATETIME_FORMAT), timezone.utc),
                # add T and Z to string timestamp so UTC is obvious.
                received_time=timezone.make_aware(datetime.strptime(unit_info[_qualify('ReceivedTime')][0]['_text'],
                                                                    SKYGISTICS_DATETIME_FORMAT),
                                                  timezone.utc).strftime(SKYGISTICS_PLUGIN_DATETIME_FORMAT),
            )
        except Exception as e:
            self.logger.exception('Error transforming skygistics unit_info')
            raise
        return observation

    def fetch_observations(self, imei, start_date, end_date=None):
        """
        Fetch observations from Skygistics for a particular collar based on imei.
        :param imei:
        :param start_date:
        :param end_date:  ignored for now, always current datetime
        :return: generator, yielding individual Observation records.
        """

        # Skygistics service will interpret date query parameters in timezone
        # of server, so we adjust here.
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
        # will be a dict with a key-value pair
        # '{http://www.w3.org/2001/XMLSchema-instance}nil': 'true'
        if ('{http://www.w3.org/2001/XMLSchema-instance}nil' in replay_data_dict[
            ('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))]
            and replay_data_dict[('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))][
                '{http://www.w3.org/2001/XMLSchema-instance}nil'] == 'true'):
            pass  # todo:  no results!
        else:
            for unit_info in \
                    replay_data_dict[('{0}ArrayOfUnitInfo'.format(SKYGISTICS_API_XMLNS))][
                        ('{0}UnitInfo'.format(SKYGISTICS_API_XMLNS))]:
                yield self._transform_to_observation(unit_info)


class SkygisticsSatellitePlugin(TrackingPlugin):

    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)

    service_username = models.CharField(max_length=50,
                                        help_text='The username for Skygistics API.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for Skygistics API.')
    service_api_url = models.CharField(max_length=50,
                                       help_text='API endpoint for Skygistics service.',
                                       default='http://skyq1.skygistics.com')

    source_plugin_reverse_relation = 'skygisticsplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')


    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        client = self._get_client()

        client.begin_session()

        try:
            # Given a latest-timestamp, reach back another 12-hours to fill in
            # any gaps.
            st = parse_date(
                self.cursor_data['latest_timestamp']) - timedelta(hours=12)
        except Exception as e:
            st = datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        end_time = datetime.now(tz=pytz.utc)

        latest_observation = None
        params = dict(imei=source.manufacturer_id, start=st, stop=end_time)
        self.logger.info('Fetching observations for {imei} {start} - {stop}'.format(
            **params
        ), extra=params)

        for unit_info in client.fetch_observations(imei=source.manufacturer_id,
                                                   start_date=st,
                                                   end_date=end_time):

            try:
                observation = self._transform(source, unit_info)
                if observation:
                    if not latest_observation or latest_observation.recorded_at < observation.recorded_at:
                        latest_observation = observation
                    yield observation
            except Exception as e:
                self.logger.exception('processing unit_info.')

        if latest_observation:
            self.cursor_data['latest_timestamp'] = latest_observation.recorded_at.isoformat(
            )

    def _transform(self, source, observation):
        return Obs(source=source,
                   recorded_at=observation.recorded_at,
                   longitude=observation.longitude,
                   latitude=observation.latitude,
                   additional=dict((k, observation._asdict().get(k)) for k in ('imei', 'voltage', 'received_at', 'temperature', 'location')))

    def _maintenance(self):
        self._sync_unit_info()

    def _login(self):
        client = self._get_client()
        client.begin_session()
        return client

    def _get_unit_list(self):
        client = self._login()
        return client.get_unit_list()

    def _get_unit_observations(self, imei, start_date, end_date):
        client = self._login()
        return client.fetch_observations(imei, start_date, end_date)

    def _get_client(self):
        return get_client(username=self.service_username,
                          password=self.service_password,
                          service_url=self.service_api_url)

    def _sync_unit_info(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        client = self._get_client()

        client.begin_session()

        unitlist = client.get_unit_list()
        for unit in unitlist:
            try:
                src = ensure_source('tracking-device', unit.imei)
                ensure_source_plugin(src, self)
                ts = unit.time
                if not ts:
                    ts = SKYGISTICS_DEFAULT_UNIT_DATETIME
                ensure_subject_source(src, ts, unit.name)
            except Exception as e:
                self.logger.exception(
                    'Error in syncing unit info {unit}'.format(unit=unit))
                raise


# Helper functions for hydrating Source and Subject for the given message.
def ensure_source(source_type, manufacturer_id):
    src, created = Source.objects.get_or_create(source_type=source_type,
                                                manufacturer_id=manufacturer_id,
                                                defaults={'model_name': 'skygistics',
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
            subject_subtype_id='elephant',
            name=subject_name,
            defaults=dict(additional=dict(region='', country='', ))
        )

        d1 = event_time - timedelta(days=30)
        d2 = d1 + timedelta(days=5 * 365)
        if sub:
            subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                          defaults=dict(assigned_range=(d1, d2), additional={
                                                                              'note': 'Created automatically during feed sync.'}))

    return subject_source
