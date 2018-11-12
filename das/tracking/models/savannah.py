import http.client
from functools import namedtuple
import time
import copy

import datetime
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz

import logging
from django.contrib.gis.db import models
from django.utils.translation import ugettext_lazy as _

from tracking.models.plugin_base import Obs, TrackingPlugin, DasPluginFetchError
from analyzers.models import CRITICAL
from analyzers.models.base import EVENT_PRIORITY_MAP

from observations.models import Subject


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
Fix = namedtuple('Fix', ['collar_id', 'longitude', 'latitude', 'recorded_at',
                         'speed', 'heading', 'temperature', 'height',
                         'hdop', 'battery'])
Fix.__new__.__defaults__ = (None, None)
field_transform = (str, float, float, __str2date, float, float, str, int,
                   float, float)

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
                        yield self.parse_line(line.decode('utf-8').strip())
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
            for alert in alerts.split('\r\n'):
                if alert:
                    # Save alert as an Event report.
                    alert = alert.split(',')
                    alert_data = alert[:-1]
                    alert_type = alert[-1]

                    reported_event_time = parse_date(
                        alert[3]).replace(tzinfo=pytz.utc)

                    # csd: handle finding the right subject (per assignment).
                    try:
                        subject = Subject.objects.get(
                            subjectsource__source__manufacturer_id=collar_id,
                            subjectsource__assigned_range__contains=reported_event_time,
                        )
                    except Subject.DoesNotExist:
                        subject_name = None
                        related_subjects = None
                    else:
                        subject_name = subject.name
                        related_subjects = [{'id': subject.id}, ]

                    event_type_info = ALERT_EVENT_TYPE_MAP.get(
                        alert_type, None)

                    if event_type_info:
                        event_type = event_type_info['event_type']
                        title = event_type_info['title_template'].format(
                            subject_name)

                        event_details = {'name': subject.name}
                        event_data = {
                            'title': title,
                            'event_type': event_type,
                            'event_details': event_details,
                            'priority': EVENT_PRIORITY_MAP.get(CRITICAL),
                            'location': {'latitude': alert[2],
                                         'longitude': alert[1]},
                            'time': reported_event_time,
                        }
                        if related_subjects:
                            event_data['related_subjects']: [{'id': subject.id, }, ]

                        from analyzers.utils import save_analyzer_event
                        save_analyzer_event(event_data)

                    # Save alerts as Observations.
                    yield self.parse_line(','.join(alert_data))

    @classmethod
    def parse_line(cls, s):
        '''
        takes a record from savanna data source and creates a Fix from it, performing necessary data-type
        conversions along the way.
        :param s:
        :return:
        '''
        dt = (c(i) for c, i in zip(field_transform, s.split(',')))
        dt = Fix(*dt)
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
            lt = fix.recorded_at
            yield self._transform((source, fix), dry_run)

        # Update cursor data if dry_run = False
        if not dry_run:
            self.cursor_data['latest_timestamp'] = lt.isoformat()

    def _transform(self, item, dry_run):
        source, o = item
        side_data = dict((k, o.__getattribute__(k)) for k in (
            'speed', 'heading', 'temperature', 'height', 'hdop', 'battery'))
        if dry_run:
            return {'source': source, 'recorded_at': o.recorded_at,
                    'latitude': o.latitude, 'longitude': o.longitude,
                    'additional': side_data}
        return Obs(source=source, recorded_at=o.recorded_at, latitude=o.latitude, longitude=o.longitude,
                   additional=side_data)
