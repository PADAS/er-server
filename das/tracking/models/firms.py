import copy
import datetime
from datetime import timedelta
from ftplib import FTP
from django.contrib.gis.geos import Polygon, MultiPolygon
from dateutil.parser import parse as parse_date

import pytz
import logging
from django.db import transaction
from django.contrib.gis.db import models
from django.contrib.contenttypes.models import ContentType

from django.contrib.gis.geos import Point
from django.utils.translation import ugettext_lazy as _

from activity.models import Event, EventType, EventDetails
from mapping.models import SpatialFeatureGroupStatic

from tracking.models.plugin_base import Obs, TrackingPlugin, DasFireEventTarget, SourcePlugin
from observations.models import Source


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


class FirmsClient(object):

    DEFAULT_FIRMS_FTP_HOSTS = [
        'nrt3.modaps.eosdis.nasa.gov', 'nrt4.modaps.eosdis.nasa.gov']

    def __init__(self, hosts=None, username=None, password=None):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''

        self.hosts = hosts or self.DEFAULT_FIRMS_FTP_HOSTS
        self.username = username
        self.password = password

        self.logger = logging.getLogger(self.__class__.__name__)

    def fetch_observations(self, region_id, last_filename=None, next_lineno=0, last_filesize=0):
        '''
        Sample filename: Northern_and_Central_Africa_MCD14DL_2015243.txt
        :param region_id:
        :param kwargs:
        :return:
        '''

        self.logger.info('Fetching FIRMS data for region_id: %s, last_filename: %s, next_lineno: %d, last_filesize: %d',
                         region_id, last_filename, next_lineno, last_filesize)
        ftp = FTP(self.hosts[0], self.username, self.password)

        try:
            ftp.cwd('FIRMS/viirs/{}'.format(region_id))

            # Go back as much as three files (three days).
            filelist = ftp.nlst()[-3:]

            try:
                i = filelist.index(last_filename)
                filelist = filelist[i:]
            except ValueError:
                filelist = filelist[-1:]
                next_lineno = 0
                last_filesize = 0

            for filename in filelist:

                # short-circuit if the file is the same size as when we last
                # read it.
                filesize = ftp.size(filename)

                self.logger.debug('Current filesize: %d', filesize)

                if filesize > last_filesize:
                    lines_buffer = []

                    _ = dict(idx=0)

                    def cb(data):
                        _['idx'] += 1
                        if _['idx'] >= next_lineno:
                            lines_buffer.append(data)

                    ftp.retrlines('RETR {}'.format(filename), cb)

                    for i, line in enumerate(lines_buffer, next_lineno):
                        try:
                            v = self.parse_line(
                                line.strip(), filename=filename, lineno=i, filesize=filesize)
                            yield v
                        except Exception as e:  # (KeyError, ValueError) as e:
                            if not line.startswith('latitude'):
                                raise

                # Any file beyond the first file will start at line zero.
                next_lineno = 0
                last_filesize = 0
        finally:
            if ftp:
                ftp.close()

    @staticmethod
    def parse_line(s, **kwargs):
        vals = [f(v) for f, v in zip(field_transform, s.split(','))]
        dt = dict(list(zip(field_names, vals)))

        # FIRMS ftp data times are UTC.
        dt['recorded_at'] = parse_date('{} {}'.format(
            dt['acq_date'], dt['acq_time'])).replace(tzinfo=pytz.UTC)
        dt.update(kwargs)
        return dt


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


class FirmsPlugin(TrackingPlugin):

    DEFAULT_REPORT_INTERVAL = timedelta(minutes=120)
    SOURCE_TYPE = 'firms'
    DEFAULT_CONFIDENCE_ALERT_LEVELS = ['nominal', 'high', ]

    service_username = models.CharField(max_length=50,
                                        help_text='The username for accessing FIRMS ftp site.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for accessing FIRMS ftp site.')

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

    @property
    def run_source_plugins(self):
        return False

    def execute(self):

        with DasFireEventTarget() as t:
            for observation in self.fetch():
                t.send(observation)
        self.save()

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

    def fetch(self):

        self.logger = logging.getLogger(self.__class__.__name__)

        if self.spatial_feature_group:
            features = self.spatial_feature_group.features.all()

            self._geo_filter = MultiPolygon(
                [f.feature_geometry for f in features]
            )
        else:
            raise ValueError(
                'Stubbornly refusing to allow no geo filter on FIRMS data ingestion.')

        # Our additional data keeps track of:
        # - the last file we've processed
        # - the next line number we want to see
        # - the size of file from our last run (so we won't waste time downloading the same file)
        last_filename = self.additional.get('last_filename', None)
        next_lineno = self.additional.get('next_lineno', 0)
        last_filesize = self.additional.get('last_filesize', 0)

        # Confidence alert levels is a list os values that might occur in the 'confidence' field and that we
        # want to create alerts for. Known values are ['low', 'nominal',
        # 'high']
        confidence_alert_levels = self.additional.get(
            'confidence_alert_levels', self.DEFAULT_CONFIDENCE_ALERT_LEVELS)

        self.client = FirmsClient(
            username=self.service_username, password=self.service_password)

        sourceplugin = self.get_sourceplugin()
        source = sourceplugin.source

        observation = None
        cnt = 0
        for observation in self.client.fetch_observations(region_id=self.firms_region_name,
                                                          last_filename=last_filename, next_lineno=next_lineno,
                                                          last_filesize=last_filesize):
            cnt += 1
            if self.pass_filter(observation):

                # Pop-off side-data from observation dict.
                additional_data = dict((k, observation.pop(k))
                                       for k in additional_fields)
                obs = Obs(source=source, recorded_at=observation['recorded_at'],
                          latitude=observation['latitude'],
                          longitude=observation['longitude'], additional=additional_data)

                # Disregard 'low-confidence' observations
                if observation.get('confidence', '') in confidence_alert_levels and self._geo_filter:
                    self.create_event(obs)

                yield obs

        # Save cursor_data (if we've processed any observations).
        if observation:
            self.additional['last_filename'] = observation['filename']
            self.additional['next_lineno'] = observation['lineno'] + 1
            self.additional['last_filesize'] = observation['filesize']

    def create_event(self, observation):

        event_details = dict((k, v) for k, v in observation.additional.items()
                             if k in ('confidence', 'frp', 'bright_ti4',
                                      'bright_ti5', 'scan', 'track'
                                      )
                             )
        event_data = dict(
            title=_('FIRMS Fire Detected'),
            updated_at=observation.recorded_at,
            priority=Event.PRI_REFERENCE,
        )

        event_key = dict(
            event_time=observation.recorded_at,
            location=Point(x=observation.longitude, y=observation.latitude),
            provenance=Event.PC_ANALYZER,
            event_type=EventType.objects.get_by_value('firms_rep'),
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
