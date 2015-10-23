__author__ = 'chris'
import logging

import base64
import http.client
import datetime
from datetime import timedelta
from dateutil.parser import parse as parse_date
import pytz
import re
from data_input.plugins.plugin import DasPlugin2, DasPlugin, PluginTarget
from data_input.models import PluginConf, PluginConfSource
from observations.models import Observation


from fastkml import kml

logger = logging.getLogger(__name__)

def config_logging():
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

config_logging()


class InreachKMLClient(object):
    def __init__(self, share_path, username, password):
        self._username = username
        self._password = password
        self._share_path = share_path

        auth = '%s:%s' % (self._username, self._password)
        auth = base64.b64encode(bytes(auth, 'utf8'))
        self._authheader = 'Basic {}'.format(auth.decode('utf8'))

    def get_data(self, imei, d1=None, d2=None):
        conn = http.client.HTTPSConnection("share.delorme.com")
        headers = {
            'authorization': self._authheader,
            'cache-control': "no-cache",
            }

        d1 = d1 or datetime.datetime.utcnow() - timedelta(days=31)
        d2 = d2 or datetime.datetime.utcnow()

        d1 = d1.strftime('%Y-%m-%dT%H:%M:%S')
        d2 = d2.strftime('%Y-%m-%dT%H:%M:%S')
        _ = "{0}?imei={1}&d1={2}&d2={3}".format(self._share_path, imei, d1, d2)
        print(_)
        conn.request("GET", _, headers=headers)
        res = conn.getresponse()
        data = res.read()

        return data.decode('utf8')

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
    'Time UTC': ('ts', __str2date),
    'Name': ('name', str),
    'Latitude': ('lat', float),
    'Longitude': ('lon', float),
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


class InreachKMLPlugin(DasPlugin):
    '''
    Inreach plugin fetches data from explorer.delorme.com for radios we've set up in DAS. Data read from Delorme's
    service is entered in DAS as observations.
    '''
    def __init__(self, config=None, target=None):
        super().__init__(config=config, target=target)

        self.logger = logging.getLogger(self.__class__.__name__)

    def _fetch(self):

        pcslist = PluginConfSource.objects.filter(plugin_conf=self.config)

        cfg = self.config.configuration

        client = InreachKMLClient(share_path=cfg['share_path'], username=cfg['username'], password=cfg['password'])

        for pcs in pcslist:
            try:
                default_starttime = datetime.datetime.now(tz=pytz.utc) - timedelta(days=31)
                _ = pcs.additional.get('latest_timestamp', None)
                latest_ts = parse_date(_)
                latest_ts = max(default_starttime, latest_ts)
            except AttributeError:
                latest_ts = default_starttime

            latest_inreach_id = pcs.additional.get('latest_inreach_id', 0)

            self.logger.debug("Fetching data for manufacturer_id %s after %s" % (pcs.source.manufacturer_id, latest_ts))

            dat = client.get_data(pcs.source.manufacturer_id, d1=latest_ts)

            for observation in client.gen_placemarks(dat):
                latest_ts = max(latest_ts, observation['ts'])

                if observation['inreach_id'] > latest_inreach_id:
                    latest_inreach_id = observation['inreach_id']
                    yield (pcs.source, observation)

            self.logger.debug("Saving latest timestamp for source %s at %s", pcs.source.manufacturer_id, latest_ts)
            pcs.additional['latest_timestamp'] = latest_ts.isoformat()
            pcs.additional['latest_inreach_id'] = latest_inreach_id
            pcs.save()



    def _transform(self, so_tuple):
        source, observation = so_tuple
        return (source, observation)

    def execute(self):
        super().execute()


if __name__ == '__main__':
    import json
    c = InreachKMLClient('/feed/Share/Odzala1', 'erikm@african-parks.org', 'odzalashare2014')
    test_imei = '300434060661240'

    c = InreachKMLClient('/feed/Share/TedSchmitt', 'teds@vulcan.com', '0dZalla')
    test_imei = '300434060291470'

    # Default start date
    start_time = datetime.datetime.utcnow() - timedelta(days=30)
    # start_time = datetime.datetime(2015, month=7, day=29, hour=7,minute=43,tzinfo=pytz.UTC)

    start_time = datetime.datetime(2015, 10, 6, 0, 14, 45, tzinfo=pytz.utc)
    after_id = 51331671

    dat = c.get_data(test_imei, d1=start_time)
    for x in c.gen_placemarks(dat):

        if x['inreach_id'] > after_id:
            print(x)









