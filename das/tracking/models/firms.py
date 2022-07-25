import logging
from datetime import datetime, timedelta

import pytz
import requests
from dateutil.parser import parse as parse_date
from shapely.ops import unary_union

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import dateparse
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventDetails, EventType
from mapping.models import SpatialFeatureGroupStatic
from observations.models import Source
from tracking.models.plugin_base import (DasFireEventTarget, Obs, SourcePlugin,
                                         TrackingPlugin)

logger = logging.getLogger(__name__)


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


def _trim(v): return str(v).strip()


# Sample:
sample_record = (33.12635, 3.3208, 300.3, 0.39, 0.44, '2018-03-20',
                 '01:06', 'N', 'nominal', '1.0NRT', 279.9, 0.6, 'N')

field_names = ('latitude', 'longitude', 'bright_ti4', 'scan', 'track', 'acq_date', 'acq_time',
               'satellite', 'confidence', 'version', 'bright_ti5', 'frp', 'daynight')

field_transform = (float, float, float, float, float, str,
                   str, str, str, _trim, float, float, str)

additional_fields = ('bright_ti4', 'bright_ti5', 'scan', 'track', 'satellite',
                     'confidence', 'version', 'frp', 'daynight')

# Data from https file:
# field_names = ('latitude', 'longitude', 'bright_ti4', 'scan', 'track', 'acq_date', 'acq_time',
# 'satellite', 'confidence', 'version', 'bright_ti5', 'frp', 'daynight')
# 29.07484,19.06227,338.1,0.43,0.46,2019-01-11,00:00,N,nominal,1.0NRT,281.5,1.9,N


FIRMS_FTP_REGIONS = (
    'Alaska',
    'Australia_NewZealand',
    'Canada',
    'Central_America',
    'Europe',
    'Global',
    'Northern_and_Central_Africa',
    'Russia_Asia',
    'SouthEast_Asia',
    'South_America',
    'South_Asia',
    'Southern_Africa',
    'USA_contiguous_and_Hawaii'
)
FIRMS_FTP_REGIONS = zip(FIRMS_FTP_REGIONS, FIRMS_FTP_REGIONS)


class FirmsClient:

    host = 'nrt3.modaps.eosdis.nasa.gov'
    data_type_and_name = 'VNP14IMGTDL_NRT'
    filename_prefix = 'SUOMI_VIIRS_C2'
    firms_data_folder = 'suomi-npp-viirs-c2'

    def __init__(self, auth_token=None, region=None):
        self.auth_token = auth_token
        self.region = region
        self.api = f'https://{self.host}/api/v2'
        self.last_storable_headers = None

    def add_auth_header(self, headers):
        headers['Authorization'] = f'Bearer {self.auth_token}'
        return headers

    def calculate_date_index(self, from_date=None):
        d = (from_date or datetime.now(tz=pytz.utc)).timetuple()
        return (d.tm_year * 1000) + d.tm_yday

    def extract_date_index(self, from_headers=None):

        if 'content-disposition' in from_headers:
            for elem in from_headers['content-disposition'].split(';'):

                try:
                    elem = elem.strip(' ')
                    if elem.startswith('filename='):
                        _, previous_filename = elem.split('=', maxsplit=1)
                        last_dateindex = previous_filename.split('.', maxsplit=1)[
                            0].split('_')[-1]
                        last_dateindex = int(last_dateindex)
                        return last_dateindex
                except (AttributeError, KeyError, IndexError):
                    # Swallow the exceptions. Let caller assume we weren't able to resolve the date.
                    logger.warning(
                        'Failed parsing headers for extracting data index for headers: %s', from_headers)

    def calculate_valid_date_indexes(self, stored_headers=None):
        # Resolve one or more date-index values to process
        todays_index = self.calculate_date_index()
        yesterdays_index = self.calculate_date_index(
            from_date=(datetime.now(tz=pytz.utc) - timedelta(days=1)))
        stored_dateindex = self.extract_date_index(
            stored_headers) if stored_headers else 0

        # Start fresh, on today's file.
        if stored_dateindex is None or stored_dateindex < yesterdays_index or stored_dateindex > todays_index:
            return [(todays_index, None), ]

        # Continuing on today's file
        if stored_dateindex == todays_index:
            return [(todays_index, stored_headers), ]

        # Continuing from yesterday and starting today.
        if stored_dateindex == yesterdays_index:
            return [
                (stored_dateindex, stored_headers),
                (todays_index, None)
            ]

    def fetch_data(self, stored_headers=None):
        '''
        If stored_headers is a dictionary, this function will evaluate it and
        attempt to resume fetching data based on its contents.

        If stored_headers is None, this function will start by downloading
        "today's" latest file.
        '''
        process_these = self.calculate_valid_date_indexes(
            stored_headers=stored_headers)

        for date_index, headers in process_these:
            # Caller will use last_storable_headers at the end of processing (to save its place).
            data, self.last_storable_headers = self.fetch_new_day_records(
                date_index, stored_headers=headers)
            yield from data

    def fetch_new_day_records(self, date_index, stored_headers=None):

        stored_headers = stored_headers or {}

        # The filename is a pattern that includes the "region" and a "date index".
        calculated_filename = f'{self.filename_prefix}_{self.region}_{self.data_type_and_name}_{date_index}.txt'

        resolved_filename = calculated_filename

        if self.region not in resolved_filename:
            raise ValueError('Logic Error: Region does not match filename')

        url = f'{self.api}/content/archives/FIRMS/{self.firms_data_folder}/{self.region}/{resolved_filename}'

        request_headers = {}
        if 'etag' in stored_headers:
            request_headers['If-None-Match'] = stored_headers['etag']

        if 'content-length' in stored_headers:
            offset = int(stored_headers['content-length'])
            request_headers['Range'] = f'bytes={offset}-'
        else:
            offset = 0

        request_headers = self.add_auth_header(request_headers)
        data = requests.get(url, headers=request_headers)

        logger.info('Handling new FIRMS response.', extra={
                    'url': url, 'status_code': data.status_code})

        # 200 or 206: read all data
        # 206: Last-modified date should reflect resource
        #     Content-Length is for partial data, so add it to the offset we used on request
        # 304: Not modified.
        # 404 Not Found: Assume the file does not yet exist.
        # 416 (Range unsatisfiable): log error message
        if data.status_code in (304, 404, 416):
            logger.info('No new FIRMS data available.', extra={
                        'url': url, 'status_code': data.status_code})
            return list(), None

        if data.status_code in (200, 206):
            storable_headers = dict((k.lower(), v)
                                    for k, v in data.headers.items())

            # Adjust the Content-Length to account for offset, so caller may use it in the future as
            # if it was a complete download.
            if data.status_code == 206:
                storable_headers['content-length'] = offset + \
                    int(storable_headers['content-length'])

            # Return a generator and a header dict that the caller may choose to cache.
            return self.generate_records(data.text.split('\n')), storable_headers

        logger.warning('Unexpected response from FIRMS web service..', extra={'url': url,
                                                                              'status_code': data.status_code})
        return [], None

    @staticmethod
    def generate_records(lines):

        for s in lines:
            # Skip header
            if s.startswith('latitude') or not s:
                continue
            try:
                vals = [f(v) for f, v in zip(field_transform, s.split(','))]
            except ValueError as ve:
                logger.error('Failed parsing FIRMS line "%s".',
                             extra={'ValueError': ve})
            else:
                rec = dict(list(zip(field_names, vals)))

                # FIRMS ftp data times are UTC.
                rec['recorded_at'] = parse_date('{} {}'.format(
                    rec['acq_date'], rec['acq_time'])).replace(tzinfo=pytz.UTC)
                yield rec


class FirmsPlugin(TrackingPlugin):

    DEFAULT_REPORT_INTERVAL = timedelta(minutes=120)
    SOURCE_TYPE = 'firms'
    DEFAULT_CONFIDENCE_ALERT_LEVELS = ['nominal', 'high', ]
    DEFAULT_ALERT_WINDOW = timedelta(hours=24)

    app_key_help_text = '''You'll need an App Key in order to get data from NASA's EarthData website. 
    Visit https://nrt4.modaps.eosdis.nasa.gov/, create a Profile, and generate an App Key (available in the Profile menu).'''
    app_key = models.CharField(max_length=1024,
                               blank=True,
                               help_text=app_key_help_text)

    ht = '''Earthdata FIRMS region name from which to fetch active fire observations. This is the region published
    by NASA's Earthdata platform. See this link for more details: https://earthdata.nasa.gov/earth-observation-data/near-real-time/firms/active-fire-data.
    '''
    firms_region_name = models.CharField(max_length=100,
                                         help_text=ht,
                                         choices=FIRMS_FTP_REGIONS)

    spatial_feature_group = models.ForeignKey(SpatialFeatureGroupStatic,
                                              related_name='+',
                                              on_delete=models.PROTECT,
                                              help_text='FIRMS data will be filtered by boundaries in this group.',
                                              null=True)
    source_plugin_reverse_relation = 'firmsplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    @property
    def run_source_plugins(self):
        return False

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__(*args, **kwargs)

    def execute(self):

        self.logger.info('Running FIRMS Plugin. region-name=%s',
                         self.firms_region_name)
        with DasFireEventTarget() as t:
            for observation in self.fetch():
                t.send(observation)
        self.save()
        logger.info('Finished FIRMS Plugin. region-name=%s',
                    self.firms_region_name)

    def get_firms_source(self):
        '''
        This plugin creates its own source.
        :return:
        '''
        source, created = Source.objects.get_or_create(
            provider=self.provider, manufacturer_id=self.firms_region_name,
            defaults=dict(source_type=self.SOURCE_TYPE, model_name='VIIRS')
        )
        return source

    def get_sourceplugin(self):
        plugin_type = ContentType.objects.get_for_model(self)
        sourceplugin, created = SourcePlugin.objects.get_or_create(defaults={},
                                                                   source=self.get_firms_source(),
                                                                   plugin_id=self.id,
                                                                   plugin_type=plugin_type)
        return sourceplugin

    @staticmethod
    def union_geofilterfeatures(geometries):
        return unary_union(geometries)

    def fetch(self):
        if self.spatial_feature_group:
            features = self.spatial_feature_group.features.all()
            geometries = [f.feature_geometry for f in features]
            try:
                self._geo_filter = self.union_geofilterfeatures(
                    geometries)
            except Exception as ex:
                logger.info(f"failed to use union_geofilterfeatures: {ex}")
                polyunion = geometries[0]
                for geom in geometries[1:]:
                    polyunion = polyunion.union(geom)
                self._geo_filter = polyunion

            logger.debug('Geometry union = %s', self._geo_filter)
        else:
            raise ValueError(
                'Stubbornly refusing to allow no geo filter on FIRMS data ingestion.')

        # Our additional data keeps track of:
        stored_headers = self.additional.get('stored_headers', None)

        # Confidence alert levels is a list os values that might occur in the 'confidence' field and that we
        # want to create alerts for. Known values are ['low', 'nominal',
        # 'high']
        confidence_alert_levels = self.additional.get(
            'confidence_alert_levels', self.DEFAULT_CONFIDENCE_ALERT_LEVELS)

        try:
            alert_window = dateparse.parse_duration(
                self.additional.get('alert_window'))
            alert_window_start_time = datetime.now(tz=pytz.utc) - alert_window
        except:
            alert_window_start_time = datetime.now(
                tz=pytz.utc) - self.DEFAULT_ALERT_WINDOW

        self.client = FirmsClient(
            region=self.firms_region_name, auth_token=self.app_key)

        sourceplugin = self.get_sourceplugin()
        source = sourceplugin.source

        try:
            for observation in self.client.fetch_data(stored_headers=stored_headers):
                if self.pass_filter(observation):

                    # Pop-off side-data from observation dict.
                    additional_data = dict((k, observation.pop(k))
                                           for k in additional_fields)
                    obs = Obs(source=source, recorded_at=observation['recorded_at'],
                              latitude=observation['latitude'],
                              longitude=observation['longitude'], additional=additional_data)

                    # Determine whether we should record an event for this
                    # observation.
                    if additional_data.get('confidence', '') in confidence_alert_levels\
                            and obs.recorded_at >= alert_window_start_time:
                        self.create_event(obs)

                    yield obs
        finally:
            # Save cursor_data (if the client provides headers).
            if self.client.last_storable_headers:
                self.additional['stored_headers'] = self.client.last_storable_headers

    def create_event(self, observation):

        event_details = dict((k, v) for k, v in observation.additional.items()
                             if k in ('confidence', 'frp', 'bright_ti4',
                                      'bright_ti5', 'scan', 'track'
                                      )
                             )

        firms_event_type = EventType.objects.get_by_value('firms_rep')

        event_data = dict(
            title=_('FIRMS Fire Detected'),
            updated_at=observation.recorded_at,
            priority=firms_event_type.default_priority,
        )

        event_key = dict(
            event_time=observation.recorded_at,
            location=Point(x=observation.longitude, y=observation.latitude),
            provenance=Event.PC_ANALYZER,
            event_type=firms_event_type,
        )

        with transaction.atomic():
            event, created = Event.objects.get_or_create(
                **event_key, defaults=event_data)

            if created:
                EventDetails.objects.create(
                    event=event, data={'event_details': event_details})

    def pass_filter(self, observation):

        if self._geo_filter:
            p = Point(y=observation['latitude'], x=observation['longitude'])
            return self._geo_filter.contains(p)
        return False

    def _transform(self, item):
        return item
