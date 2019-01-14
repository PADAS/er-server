import logging
import http.client
from typing import NamedTuple
import time
import copy
import datetime
from datetime import timedelta

from django.contrib.gis.db import models
from django.utils.translation import ugettext_lazy as _
from dateutil.parser import parse as parse_date
import pytz

from tracking.models.plugin_base import Obs, TrackingPlugin, DasPluginFetchError
from observations.models import Observation


class STObservation(NamedTuple):
    collar_id: str
    longitude: float
    latitude: float
    recorded_at: datetime.datetime
    speed: float
    heading: float
    temperature: str
    height: int
    hdop: float = None
    battery: float = None


class STAlert(NamedTuple):
    collar_id: str
    longitude: float
    latitude: float
    recorded_at: datetime.datetime
    speed: float
    heading: float
    temperature: str
    height: int
    hdop: float
    battery: float
    device_alert: str
    is_alert: bool


# Map Savannah alert keys to DAS Event Type.
ALERT_EVENT_TYPE_MAP = {
    'Immobility Alert': {
        'event_type': 'immobility',
        'title_template': _('{} is immobile')
    },
    'None': {
        'event_type': 'immobility_all_clear',
        'title_template': _('{} is moving')
    }

}


class SavannaClient(object):

    def __init__(self, host=None, username=None, password=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.username = username
        self.password = password
        self.host = host

    @staticmethod
    def str2date(d, replace_tzinfo=pytz.utc):
        '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
        return parse_date(d).replace(tzinfo=replace_tzinfo)

    def fetch_observations(self, collar_id, start_time, end_time=None):
        '''
        Fetch observations from Savannah data-source for a particular collar.
        :param collar_id: collar_id from trackingmaster record.
        :param start_time: unix timestamp for earliest data to fetch.
        :param end_time: <not used>
        :return: generator, yielding individual records.
        '''

        self.logger.info(
            'Fetching from SavannahTracking for collar_id: %s, start_time: %s', collar_id, start_time)
        conn = http.client.HTTPConnection(self.host, timeout=15)

        payload = dict(uid=self.username, pwd=self.password,
                       unixtime=str(start_time), collar=collar_id)

        payload = ['='.join((k, v)) for k, v in payload.items()]
        payload = '&'.join(payload)

        headers = {'accept': "*/*",
                   'content-type': 'application/x-www-form-urlencoded'
                   }

        conn.request("POST", "/savannah/get_data.asp", payload, headers)

        res = conn.getresponse()
        saveline = None
        if res.status == http.client.OK:
            self.logger.info(
                'Fetch OK from SavannahTracking for collar_id: %s, start_time: %s', collar_id, start_time)

            for line in res:
                try:
                    if line != saveline:  # We occassionally see duplicate records in results.
                        yield self.parse_line(STObservation, line.decode('utf-8').strip())
                except Exception as e:
                    self.logger.exception(
                        'Failed to parse line for collar_id: %s, line: [%s]', collar_id, line)
                saveline = line
        else:
            msg = 'Failed to get data from Savannah Tracking API for collar_id: %s. Result status: %d' % (collar_id,
                                                                                                          res.status)
            self.logger.error(msg)
            raise DasPluginFetchError(msg)

        yield from self.fetch_alerts(collar_id, start_time=start_time, end_time=end_time)

    def fetch_alerts(self, collar_id, start_time, end_time=None):

        # Get Savannah collar alarms.
        self.logger.info('Getting Savannah collar alarms for collar_id: '
                         '{}'.format(collar_id))
        connection = http.client.HTTPConnection(self.host, timeout=15)
        connection.request(
            "GET", "/savannah/get_alerts.asp?uid={}&pwd={}&start_time={}&"
                   "end_time={}&collar={}".format(
                       self.username, self.password, start_time, str(
                           time.time()),
                       collar_id)
        )

        alerts_response = connection.getresponse()
        if alerts_response.status == 200:
            alerts = alerts_response.read()
            alerts = alerts.decode('utf-8').strip()
            # Split response and set device_alert type according to event_type
            for alert in alerts.split('\r\n'):
                alert = alert.split(',')
                alert_data = alert[:-1]
                alert_type = alert[-1]
                event_type_info = ALERT_EVENT_TYPE_MAP.get(
                    alert_type, None)

                if not event_type_info:
                    self.logger.info(f'Unsupported ST alert type {alert_type}')
                    continue

                device_alert = event_type_info['event_type']

                # Check if alert api is returning hdop, battery or not
                # If not, assign value as zero
                while len(STObservation._fields) - len(alert_data) > 0:
                    alert_data.append('')

                # Atlast push device_alert and is_alert
                alert_data.append(device_alert)
                alert_data.append('true')
                yield self.parse_line(STAlert, ','.join(alert_data))

    @classmethod
    def parse_line(cls, observation_class, s):
        '''
        takes a record from savanna data source and creates a Fix from it, performing necessary data-type
        conversions along the way.
        :param s:
        :return:
        '''
        dt = ((cls.str2date(i) if c == datetime.datetime else c(i)) if i != '' else None
              for c, i in zip(observation_class._field_types.values(), s.split(',')))
        dt = observation_class(*dt)
        return dt


class SavannahPlugin(TrackingPlugin):
    '''
    Fetch data from Savannah Tracking API.
    '''
    DEFAULT_START_OFFSET = timedelta(days=14)
    DEFAULT_REPORT_INTERVAL = timedelta(minutes=30)

    service_username = models.CharField(max_length=50,
                                        help_text='The username for querying the Savannah Tracking service.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for querying the Savannah Tracking service.')
    service_api_host = models.CharField(max_length=50,
                                        help_text='the ip-address or host-name for the Savannah Tracking service.')

    def fetch(self, source, cursor_data=None, dry_run=False):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        client = SavannaClient(username=self.service_username,
                               password=self.service_password,
                               host=self.service_api_host)

        try:
            st = parse_date(self.cursor_data['latest_timestamp'])
        except Exception as e:
            st = datetime.datetime.now(tz=pytz.UTC) - self.DEFAULT_START_OFFSET

        lt = st
        st = int(st.timestamp()) + 1

        self.logger.debug('Fetching data for collar_id %s',
                          source.manufacturer_id)

        now = pytz.utc.localize(datetime.datetime.utcnow())
        for fix in client.fetch_observations(source.manufacturer_id, start_time=st):
            if fix.recorded_at > now:
                self.logger.warning(
                    'Savannah plugin encountered a fix from the future: {0}'.format(fix))
                continue

            # If observation has been received from alert api than
            # is_alert=True
            if isinstance(fix, STAlert) and fix.is_alert:
                # Filter observation based on timestamp, source.
                # If observation exist, update observation's additional field
                # else yield Obs
                obs = Observation.objects.filter(
                    source=source, recorded_at=fix.recorded_at).first()
                if obs:
                    additional = obs.additional
                    additional['device_alert'] = fix.device_alert
                    obs.additional = additional
                    obs.save()
                    continue
            lt = fix.recorded_at
            yield self._transform((source, fix), dry_run)

        # Update cursor data if dry_run = False
        if not dry_run:
            self.cursor_data['latest_timestamp'] = lt.isoformat()

    def _transform(self, item, dry_run):
        source, o = item
        side_data = dict((k, o.__getattribute__(k)) for k in (
            'speed', 'heading', 'temperature', 'height', 'hdop', 'battery'))

        # Check If observation has been received from alert api
        # than set device_alert key and it's value in additional field
        if isinstance(o, STAlert) and o.is_alert:
            side_data['device_alert'] = o.device_alert
        if dry_run:
            return {'source': source, 'recorded_at': o.recorded_at,
                    'latitude': o.latitude, 'longitude': o.longitude,
                    'additional': side_data}
        return Obs(source=source, recorded_at=o.recorded_at, latitude=o.latitude, longitude=o.longitude,
                   additional=side_data)
