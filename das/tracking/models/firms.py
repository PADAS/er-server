import copy
from datetime import timedelta
from ftplib import FTP
from django.contrib.gis.geos import Polygon, Point, MultiPolygon
from dateutil.parser import parse as parse_date

import pytz
import logging
from django.contrib.gis.db import models

from tracking.models.plugin_base import Obs, TrackingPlugin

def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from FIRMS datasource.
field_names = ('latitude', 'longitude', 'brightness', 'scan', 'track', 'acq_date', 'acq_time', 'satellite', 'confidence', 'version', 'bright_t31', 'frp')
field_transform = (float, float, float, float, float, str, str, str, int, str, float, float)

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

    def fetch_observations(self, region_id, **kwargs):

        '''
        Sample filename: Northern_and_Central_Africa_MCD14DL_2015243.txt
        :param region_id:
        :param kwargs:
        :return:
        '''
        ftp = FTP(self.hosts[0], self.username, self.password)

        ftp.cwd('FIRMS/{}'.format(region_id))

        latest = ftp.nlst()[-1]

        # I want a universal sequence id for lines in this file, so I'll concatenate the file's name's date component
        # with the line number.
        file_sequence = int(latest.split('_')[-1].split('.')[0])
        file_sequence *= 1000000

        after_offset = kwargs.get('after_offset', -1)
        # fsize = ftp.size(latest)
        # print("File size : %s" % (fsize,))

        # store lines in an array. Switch to a tmp file if the files turn out to be very large.
        lines_buffer = []
        def cb(data):
            lines_buffer.append(data)

        ftp.retrlines('RETR {}'.format(latest), cb)

        for i, line in enumerate(lines_buffer):
            try:
                if i > after_offset:
                    v = self.parse_line(line.strip(), offset=file_sequence+i)
                    yield v
            except ValueError:
                if not line.startswith('latitude'):
                    raise


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


        try:
            hi_sequence = parse_date(self.cursor_data['highest_sequence'])
        except:
            hi_sequence = -1

        self.logger.info("Fetching data for manufacturer_id %s" % (source.manufacturer_id,))

        self.client = FirmsClient(username=self.service_username, password=self.service_password)

        for observation in self.client.fetch_observations(region_id=source.manufacturer_id, after_offset=hi_sequence):
            hi_sequence = observation['offset']
            print(observation)
            if self.pass_filter(observation):

                # Pop-off side-data from observation dict.
                additional_data = dict((k, observation.pop(k)) for k in additional_fields)
                yield Obs(source=source, recorded_at=observation['recorded_at'], latitude=observation['latitude'],
                          longitude=observation['longitude'], additional=additional_data)

        # Save cursor_data
        self.cursor_data['highest_sequence'] = hi_sequence



    def pass_filter(self, observation):
        if self._geo_filter:
            p  = Point(y=observation['latitude'], x=observation['longitude'])
            return self._geo_filter.contains(p)
        return True

    def _transform(self, item):
        return item


