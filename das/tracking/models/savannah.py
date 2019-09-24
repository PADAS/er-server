import copy
import datetime
import json
import logging

from datetime import timedelta
from typing import NamedTuple
import pytz
from dateutil.parser import parse as parse_date
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.utils.translation import ugettext_lazy as _

from observations.models import Observation
from tracking.models.plugin_base import (DasPluginFetchError, Obs,
                                         SourcePlugin, TrackingPlugin)
import requests


class STObservation(NamedTuple):
    collar_id: str
    record_index: int
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
    record_index: int
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

REQUEST_TO_URL = {
    "authenticate": "/savannah_data/data_auth",
    "data_download": "/savannah_data/data_request",
    "exceptions_download": "/savannah_data/data_request"
}


class SavannaClient(object):

    def __init__(self, host=None, username=None, password=None, record_index=0):

        self.logger = logging.getLogger(self.__class__.__name__)

        self.username = username
        self.password = password
        self.host = host
        self.record_index = record_index

    @staticmethod
    def str2date(d, replace_tzinfo=pytz.utc):
        '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
        return parse_date(d).replace(tzinfo=replace_tzinfo)

    def make_request(self, collar_id, request):
        """ Make request to savannah api with multiple request types """
        payload = dict(uid=self.username, pwd=self.password,
                       request=request, collar=collar_id, record_index=self.record_index)
        return requests.post(self.host + REQUEST_TO_URL[request], data=payload)

    def select_data(self, collar_id, record):
        """ Select and order data received from savannah api """
        return [collar_id, record["record_index"], record["longitude"], record["latitude"],
                record["record_time"], record["speed"], record["heading"], record["temperature"],
                record["h_accuracy"], record["hdop"], record["battery"]]

    def fetch_observations(self, collar_id):
        '''
        Fetch observations from Savannah data-source for a particular collar.
        :param collar_id: collar_id from trackingmaster record.
        :return: generator, yielding individual records.
        '''
        self.logger.info(
            'Fetching from SavannahTracking for collar_id: %s', collar_id)
        res = self.make_request(collar_id, "data_download")
        if res.status_code == 200:
            self.logger.info(
                'Fetch OK from SavannahTracking for collar_id: %s', collar_id)
            all_records = json.loads(res.text)["records"]
            for line in all_records:
                yield self.parse_line(STObservation, self.select_data(collar_id, line))
        else:
            msg = 'Failed to get data from Savannah Tracking API for collar_id: %s. Result status: %d' % (collar_id,
                                                                                                          res.status)
            self.logger.error(msg)
            raise DasPluginFetchError(msg)
        yield from self.fetch_alerts(collar_id)

    def fetch_alerts(self, collar_id):

        # Get Savannah collar alarms.
        self.logger.info('Getting Savannah collar alarms for collar_id: '
                         '{}'.format(collar_id))
        alerts_response = self.make_request(collar_id, "exceptions_download")
        if alerts_response.status_code == 200:
            alerts = json.loads(alerts_response.text)["records"]

            # Set device_alert type according to event_type
            for alert in alerts:
                alert_type = alert["exception_type"]
                event_type_info = ALERT_EVENT_TYPE_MAP.get(
                    alert_type.title(), None)

                if not event_type_info:
                    self.logger.info(f'Unsupported ST alert type {alert_type}')
                    continue

                device_alert = event_type_info['event_type']
                alert = self.select_data(collar_id, alert)

                # At last push device_alert and is_alert
                alert.append(device_alert)
                alert.append('true')
                yield self.parse_line(STAlert, alert)

    @classmethod
    def parse_line(cls, observation_class, s):
        '''
        takes a record from savanna data source and creates a Fix from it, performing necessary data-type
        conversions along the way.
        :param s:
        :return:
        '''
        dt = ((cls.str2date(i) if c == datetime.datetime else c(i))
              for c, i in zip(observation_class._field_types.values(), s))
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

    source_plugin_reverse_relation = 'savannahplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

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
        for fix in client.fetch_observations(source.manufacturer_id):
            self.cursor_data["record_index"] = fix.record_index

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
