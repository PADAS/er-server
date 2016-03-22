import copy
from datetime import timedelta
from ftplib import FTP
from django.contrib.gis.geos import Polygon, Point, MultiPolygon
from dateutil.parser import parse as parse_date

import pytz
import logging
from django.contrib.gis.db import models

from django.contrib.gis.geos import Point
from django.db import transaction

from activity.models import Event, EventAttachment

from tracking.models.plugin_base import Obs, TrackingPlugin

def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)

_trim = lambda v: str(v).strip()
# Helpers for parsing lines from FIRMS datasource.
field_names = ('latitude', 'longitude', 'brightness', 'scan', 'track', 'acq_date', 'acq_time', 'satellite', 'confidence', 'version', 'bright_t31', 'frp')
field_transform = (float, float, float, float, float, str, str, str, int, _trim, float, float)

additional_fields = ('brightness', 'scan', 'track', 'satellite', 'confidence', 'version', 'bright_t31', 'frp')


class FirmsClient(object):

    DEFAULT_FIRMS_FTP_HOSTS = ['nrt1.modaps.eosdis.nasa.gov', 'nrt2.modaps.eosdis.nasa.gov']

    def __init__(self, hosts=None, username=None, password=None):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''


        self.hosts = hosts or self.DEFAULT_FIRMS_FTP_HOSTS
        self.username = username
        self.password = password

        self.logger = logging.getLogger(self.__class__.__name__)



    def fetch_observations(self, region_id, current_filename=None, next_lineno=0, last_filesize=0):

        '''
        Sample filename: Northern_and_Central_Africa_MCD14DL_2015243.txt
        :param region_id:
        :param kwargs:
        :return:
        '''


        self.logger.debug('Fetching FIRMS data for region_id: %s, current_filename: %s, next_lineno: %d, last_filesize: %d',
                          region_id, current_filename, next_lineno, last_filesize)
        ftp = FTP(self.hosts[0], self.username, self.password)

        try:
            ftp.cwd('FIRMS/{}'.format(region_id))

            # Go back as much as three files (three days).
            filelist = ftp.nlst()[-3:]

            try:
                i = filelist.index(current_filename)
                filelist = filelist[i:]
            except ValueError:
                filelist = filelist[-1:]
                next_lineno = 0
                last_filesize=0


            for filename in filelist:

                # short-circuit if the file is the same size as when we last read it.
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
                            v = self.parse_line(line.strip(), filename=filename, lineno=i, filesize=filesize)
                            yield v
                        except ValueError:
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
        '''
        takes a record from savanna data source and creates a Fix from it, performing necessary data-type
        conversions along the way.
        :param s:
        :return:
        '''
        vals = (c(i) for c, i in zip(field_transform, s.split(',')))
        dt = dict((k, v) for k, v in zip(field_names, vals))

        # FIRMS ftp data times are UTC.
        dt['recorded_at'] = parse_date('{} {}'.format(dt['acq_date'], dt['acq_time'])).replace(tzinfo=pytz.UTC)
        dt.update(kwargs)
        return dt


class FirmsPlugin(TrackingPlugin):

    DEFAULT_START_OFFSET = timedelta(days=14)

    service_username = models.CharField(max_length=50,
                                       help_text='The username for accessing FIRMS ftp site.')
    service_password = models.CharField(max_length=50,
                                        help_text='The password for accessing FIRMS ftp site.')


    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        polygons = self.additional.get('polygons', None)

        if polygons:
            polygons = list((Polygon(p) for p in polygons))
            _ = MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
            self._geo_filter = _.prepared
        else:
            self._geo_filter = None

        # Our cursor data keeps track of:
        # - the last file we've processed
        # - the next line number we want to see
        # - the size of file from our last run (so we won't waste time downloading the same file)
        last_filename = self.cursor_data.get('current_filename', None)
        next_lineno = self.cursor_data.get('next_lineno', 0)
        last_filesize = self.cursor_data.get('last_filesize', 0)

        self.logger.info("Fetching data for manufacturer_id %s" % (source.manufacturer_id,))

        self.client = FirmsClient(username=self.service_username, password=self.service_password)

        for observation in self.client.fetch_observations(region_id=source.manufacturer_id,
                                                          current_filename=last_filename, next_lineno=next_lineno,
                                                          last_filesize=last_filesize):

            if self.pass_filter(observation):

                # Pop-off side-data from observation dict.
                additional_data = dict((k, observation.pop(k)) for k in additional_fields)
                obs = Obs(source=source, recorded_at=observation['recorded_at'], latitude=observation['latitude'],
                          longitude=observation['longitude'], additional=additional_data)
                self.create_event(obs)
                yield obs

        # Save cursor_data (if we've processed any observations).
        if observation:
            self.cursor_data['current_filename'] = observation['filename']
            self.cursor_data['next_lineno'] = observation['lineno'] + 1
            self.cursor_data['last_filesize'] = observation['filesize']

    def create_event(self, observation):

        location = Point(x=observation.longitude, y=observation.latitude)

        with transaction.atomic():
            event = Event(
                event_type=Event.ET_FIRE,
                provenance=Event.SENSOR,
                attributes=observation.additional,
                location=location,
                priority=Event.PRI_IMPORTANT,
                name='Fire detected by satellite',
                description='Fire detected, with confidence: {confidence}, brightness: {brightness}, frp: {frp}'.format(**observation.additional)
            )
            event.save()
            return event



    def pass_filter(self, observation):
        if self._geo_filter:
            p  = Point(y=observation['latitude'], x=observation['longitude'])
            return self._geo_filter.contains(p)
        return True

    def _transform(self, item):
        return item


