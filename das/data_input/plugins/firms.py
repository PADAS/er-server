"""
 Fetch and transform Savannah data into DAS input format
"""
import copy

import http.client
import ssl
from functools import namedtuple
from observations.models import Observation, Source
from .plugin import DasPlugin, PluginTarget
import datetime, time
from data_input.models import PluginConf, PluginConfSource
from ftplib import FTP

from dateutil.parser import parse as parse_date
import pytz


def __str2date(d, replace_tzinfo=pytz.utc):
    '''Helper function to parse a naive date and assume it's in replace_tzinfo.'''
    return parse_date(d).replace(tzinfo=replace_tzinfo)


# Helpers for parsing lines from Savanna datasource.
field_names = ('lat', 'lon', 'brightness', 'scan', 'track', 'acq_date', 'acq_time', 'satellite', 'confidence', 'version', 'bright_t31', 'frp')
field_transform = (float, float, float, float, float, str, str, str, int, str, float, float)


# class SavannaException(Exception):
#     pass

class FirmsClient(object):

    def __init__(self, config={}):
        '''
        Configuration is given by the plugin. Probably saved in PluginConf record.
        :param config: must include 'credentials' and 'host'
        '''
        self.host = config.get('host', 'nrt1.modaps.eosdis.nasa.gov')
        self.username = config.get('username', 'chrisdoehring')
        self.password = config.get('password', '[Rhubarb91$]')


    # def http_fetch_observations(self, region_id, start_time=None, end_time=None):
    #     '''
    #     Fetch observations from Savannah data-source for a particular collar.
    #     :param collar_id: collar_id from trackingmaster record.
    #     :param start_time: unix timestamp for earliest data to fetch.
    #     :param end_time: <not used>
    #     :return: generator, yielding individual records.
    #     '''
    #
    #     conn = http.client.HTTPSConnection(self.host)
    #     conn.request("GET", "/active_fire/text/%s_24h.csv" % (region_id,))
    #     res = conn.getresponse()
    #     if res.status == http.client.OK:
    #         line = res.readline()
    #         for line in res:
    #             yield self.parse_line(line.decode('utf8').strip())


    def fetch_observations(self, region_id, **kwargs):

        '''
        Sample filename: Northern_and_Central_Africa_MCD14DL_2015243.txt
        :param region_id:
        :param kwargs:
        :return:
        '''
        ftp = FTP(self.host, self.username, self.password)

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


    @classmethod
    def parse_line(cls, s, **kwargs):
        '''
        takes a record from savanna data source and creates a Fix from it, performing necessary data-type
        conversions along the way.
        :param s:
        :return:
        '''
        vals = (c(i) for c, i in zip(field_transform, s.split(',')))
        dt = dict((k, v) for k, v in zip(field_names, vals))

        dt['ts'] = parse_date('{} {}'.format(dt['acq_date'], dt['acq_time']))
        dt.update(kwargs)
        return dt


def unixtimestamp(d):
    return int(time.mktime(d.timetuple()))

DEFAULT_START_TIME = datetime.datetime(2015, 8, 1, tzinfo=pytz.utc).isoformat()

class FirmsPlugin(DasPlugin):

    def __init__(self, plugin_conf, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self._config = plugin_conf
        self.client = FirmsClient() #config=self._config.configuration)

    def _fetch(self):

        sources = Source.objects.filter(source_type='firms')
        for source in sources:

            try:
                pcs = PluginConfSource.objects.get(source=source, plugin_conf=self._config)
            except PluginConfSource.DoesNotExist:
                pcs = PluginConfSource(source=source, plugin_conf=self._config, additional=dict(highest_sequence=-1))
                pcs.save()

            print("Fetching data for manufacturer_id %s" % (source.manufacturer_id,))
            hi_sequence = pcs.additional['highest_sequence']
            for observation in self.client.fetch_observations(region_id=source.manufacturer_id, after_offset=hi_sequence):
                hi_sequence = observation['offset']
                yield (source, observation)

            pcs.additional['highest_sequence'] = hi_sequence
            pcs.save()

        x = input('Go on?')


    def _transform(self, so_tuple):
        source, observation = so_tuple
        return (source, observation)

    def execute(self):
        super().execute()


class FirmsTarget(PluginTarget):

    def _handle_item(self, item):
        (source, obs) = item
        Observation.objects.add_observation(source, obs)
        print(obs)


