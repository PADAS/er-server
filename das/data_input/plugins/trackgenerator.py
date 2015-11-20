from django.contrib.gis.geos import Polygon, Point, MultiPolygon
from functools import namedtuple
import random

import geopy
import geopy.distance

from data_input.models import PluginConfSource
from data_input.plugins.plugin import DasPlugin, Obs

import logging
import datetime
from datetime import timedelta
import pytz
from dateutil.parser import parse as parse_date

Config = namedtuple('Config', ('name', 'manufacturer_id', 'boundaries',))


class RandomMover(object):
    '''
    Something that could behave a little like a moving animal. Started at a psuedo-random point.
    '''
    def __init__(self, boundaries, initial_position=None):

        polygons = boundaries.get('polygons', None)

        if polygons:
            polygons = list((Polygon(p) for p in polygons))
            _ = MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
            self._geo_filter = _ #.prepared
        else:
            self._geo_filter = None

        if initial_position is not None:
            self._current_position = geopy.Point(latitude=initial_position['latitude'],
                                                 longitude=initial_position['longitude'])
        else:
            d = self._pick_position()

    def _pick_position(self):
        '''
        Polygon.point_on_surface will likely give me the center point.
        :return:
        '''
        _ = self._geo_filter.point_on_surface
        self._current_position= geopy.Point(longitude=_.x, latitude=_.y)
        for x in range(0, 100):
            self.next_point()

    def next_point(self):

        change_k = random.random() #*3.0
        d = geopy.distance.VincentyDistance(kilometers=change_k)
        change_bearing = random.random()*360.0

        # self.logger.debug('change_k: {0}, change_b: {1}'.format(change_k, change_bearing))

        x = d.destination(point=self._current_position, bearing=change_bearing)

        for _ in range(0, 30):
            if self.pass_filter(x.latitude, x.longitude):
                break
            change_bearing = (change_bearing+10.0) % 360.0
            x = d.destination(point=self._current_position, bearing=change_bearing)
        else:
            raise Exception("I'm stuck! I tried 30 times, but I can't find a path back into my boundaries.")

        self._current_position = x
        return self._current_position

    def pass_filter(self, lat, lon):
        if self._geo_filter:
            p  = Point(lon, lat)
            return self._geo_filter.contains(p)
        return True


class DemoPlugin(DasPlugin):

    plugin_key = 'demo-wildlife'
    def __init__(self, config=None, target=None):
        super().__init__(config=config, target=target)
        self.logger = logging.getLogger(self.__class__.__name__)

    def _fetch(self):

        conf_sources = PluginConfSource.objects.filter(plugin_conf=self.config)
        for conf_source in conf_sources:

            try:
                default_starttime = datetime.datetime.now(tz=pytz.utc) - timedelta(days=14)
                _ = conf_source.additional.get('latest_timestamp', None)
                latest_ts = parse_date(_)
                latest_ts = max(default_starttime, latest_ts)

            except AttributeError:
                latest_ts = default_starttime

            try:
                source = conf_source.source
                self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)

                boundaries = conf_source.additional['boundaries']

                last_location = conf_source.additional.get('last_location')
                r = RandomMover(boundaries=boundaries, initial_position=last_location)

                next_ts = latest_ts + timedelta(hours=1)

                now = datetime.datetime.now(tz=pytz.utc)
                lt = latest_ts
                observation = None
                while next_ts < now:
                    p = r.next_point()

                    observation = {
                        'source': source,
                        'latitude': p.latitude,
                        'longitude': p.longitude,
                        'recorded_at': next_ts,
                        'additional': None

                    }

                    observation = Obs(**observation)
                    yield observation
                    next_ts = next_ts + timedelta(minutes=random.randint(58, 62))

                if observation:
                    # Save 'cursor' info for this source.
                    conf_source.additional['latest_timestamp'] = observation.recorded_at.isoformat()
                    conf_source.additional['last_location'] = {'latitude': observation.latitude,
                                                               'longitude': observation.longitude
                                                               }
                    conf_source.save()
                    self.logger.info("Saved config for collar_id %s" % (source.manufacturer_id,))

            except Exception as e:
                self.logger.exception("Error fetching savanna collar data")

    def _transform(self, item):
        return item

    def execute(self):
        super().execute()



