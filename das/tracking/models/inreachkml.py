import logging
import copy

import base64
import ssl
import http.client
import datetime
from datetime import timedelta
from dateutil.parser import parse as parse_date
import pytz
import re
from fastkml import kml
from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericRelation


from tracking.models.plugin_base import Obs, TrackingPlugin, SourcePlugin, DasPluginFetchError

logger = logging.getLogger(__name__)


def config_logging():
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


config_logging()


class InreachKMLClient(object):

    DEFAULT_START_OFFSET = timedelta(days=31)

    def __init__(self, share_path, username, password):
        self._username = username
        self._password = password
        self._share_path = share_path

        auth = '%s:%s' % (self._username, self._password)
        auth = base64.b64encode(bytes(auth, 'utf8'))
        self._authheader = 'Basic {}'.format(auth.decode('utf8'))

    def get_data(self, imei=None, d1=None, d2=None):
        conn = http.client.HTTPSConnection(
            "share.garmin.com", context=ssl._create_unverified_context())
        headers = {
            'authorization': self._authheader,
            'cache-control': "no-cache",
        }

        d1 = d1 or datetime.datetime.utcnow() - self.DEFAULT_START_OFFSET
        d2 = d2 or datetime.datetime.utcnow()

        d1 = d1.strftime('%Y-%m-%dT%H:%M:%S')
        d2 = d2.strftime('%Y-%m-%dT%H:%M:%S')
        url = "{0}?d1={1}&d2={2}".format(self._share_path, d1, d2)

        if imei:
            url = url + '&imei={0}'.format(imei)

        conn.request("GET", url, headers=headers)
        res = conn.getresponse()
        data = res.read()
        data_str = data.decode('utf8')

        if res.code != 200:
            msg = f'Failed to get InReach KML feed for {imei} code {res.code} msg {data_str}'
            logger.warning(msg, extra=dict(imei=imei, status=res.code))
            raise DasPluginFetchError(msg)

        return data_str

    def gen_placemarks(self, xmlstring):

        k = kml.KML()
        k.from_string(xmlstring)

        features = [x for x in k.features()]

        featureFolders = [x for x in features[0].features()]

        if len(featureFolders) > 0:
            f = featureFolders[0]

            for pm in f.features():
                if hasattr(pm.extended_data, 'elements'):
                    yield dict(safe_map(p1.name, p1.value) for p1 in pm.extended_data.elements)


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


def __str2boolean(v):
    return v.lower() in ("true", "yes", "t", "1")


def __str2elevation(v):
    '''Expecting a string like "102.4 m from MSL"'''
    return __extract_value_and_units(v, r'^(-?[\d\.]+)\s*(.*)')


def __extract_value_and_units(v, expr):
    # Generalized for parsing a string like "<numeric> <units>"
    ret = dict(desc=v)
    try:
        data = (amt, units) = re.match(expr, v).groups()
        ret.update(dict(zip(('val', 'units'), (float(amt), units))))
    except AttributeError:
        pass
    return ret


def __str2velocity(v):
    '''Expecting a string like "1.4 km/h"'''
    return __extract_value_and_units(v, r'^([\d\.]+)\s*(.*)')


field_map = {
    'Time UTC': ('recorded_at', __str2date),
    'Name': ('name', str),
    'Latitude': ('latitude', float),
    'Longitude': ('longitude', float),
    'IMEI': ('imei', str),
    'Elevation': ('elevation', __str2elevation),
    'Velocity': ('velocity', __str2velocity),
    'Id': ('inreach_id', int),
    'Course': ('course', str),
    'Event': ('event_desc', str),
    'In Emergency': ('in_emergency', __str2boolean),
    'Text': ('text', str),
    'Map Display Name': ('display_name', str)
}


def safe_map(k, v):
    if k in field_map:
        return field_map[k][0], field_map[k][1](v)
    return k.lower().replace(' ', '_'), v


class InreachKMLPlugin(TrackingPlugin):
    '''
    Fetch data from Inreach KML share.
    '''
    DEFAULT_START_OFFSET = timedelta(days=14)

    service_share_path = models.CharField(max_length=50,
                                          help_text='share_path for InReach KML share.')
    service_password = models.CharField(max_length=50,
                                        help_text='Password for InReach KML share.')
    service_username = models.CharField(max_length=50,
                                        help_text='Username for InReach KML share.')

    source_plugin_reverse_relation = 'inreachkmlplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    DEFAULT_REPORT_INTERVAL = timedelta(minutes=7)

    class Meta:
        verbose_name = "inReach Personal plugin"
        verbose_name_plural = "inReach Personal plugins"

    def should_run(self, source_plugin):

        # Don't bother running now if less than 20 minutes has passed since the
        # latest fix.
        try:
            latest_timestamp = source_plugin.cursor_data.get(
                'latest_timestamp')
            if not latest_timestamp:
                return True
            latest_timestamp = parse_date(latest_timestamp)

            if (datetime.datetime.now(tz=pytz.UTC) - self.DEFAULT_REPORT_INTERVAL) > latest_timestamp:
                return True

        except Exception as e:
            return True
        else:
            return False

    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        client = InreachKMLClient(share_path=self.service_share_path,
                                  username=self.service_username,
                                  password=self.service_password)

        try:
            default_starttime = datetime.datetime.now(
                tz=pytz.utc) - InreachKMLClient.DEFAULT_START_OFFSET
            _ = self.cursor_data['latest_timestamp']
            latest_ts = parse_date(_)
            latest_ts = max(default_starttime, latest_ts)
        except Exception:
            latest_ts = default_starttime

        latest_inreach_id = self.cursor_data.get('latest_inreach_id', 0)

        self.logger.debug("Fetching data for manufacturer_id %s after %s" % (
            source.manufacturer_id, latest_ts))

        dat = client.get_data(source.manufacturer_id, d1=latest_ts)
        if not dat:
            self.logger.debug("No data found for manufacturer_id %s after %s" % (
                source.manufacturer_id, latest_ts))
            return

        for observation in client.gen_placemarks(dat):
            latest_ts = max(latest_ts, observation['recorded_at'])

            if observation['inreach_id'] > latest_inreach_id:
                latest_inreach_id = observation['inreach_id']
                yield self._transform(source, observation)

        # Save cursor_data
        self.logger.debug(
            "Saving latest timestamp for source %s at %s", source.manufacturer_id, latest_ts)
        self.cursor_data['latest_timestamp'] = latest_ts.isoformat()
        self.cursor_data['latest_inreach_id'] = latest_inreach_id

    @staticmethod
    def _transform(source, o):
        # Copy any none-standard fields into Obs.additional
        side_data = dict((k, o.get(k))
                         for k in o.keys() if k not in Obs._fields)
        return Obs(source=source, recorded_at=o.get('recorded_at'),
                   latitude=o.get('latitude'),
                   longitude=o.get('longitude'),
                   additional=side_data)
