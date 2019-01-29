import random
import copy

from functools import namedtuple
import datetime
from datetime import timedelta
from dateutil.parser import parse as parse_date
import pytz
from django.contrib.gis.geos import Polygon, Point, MultiPolygon
import logging
from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericRelation

import geopy
import geopy.distance

from tracking.models.plugin_base import Obs, TrackingPlugin, SourcePlugin

import mapping.models

Config = namedtuple('Config', ('name', 'manufacturer_id', 'boundaries',))


class RandomMover(object):

    DEFAULT_SPEED_MPS = 1.3 # roughly 3 miles per hour
    DEFAULT_INTERVAL_SECONDS = 3600
    '''
    Something that could behave a little like a moving animal. Started at a psuedo-random point.
    '''
    def __init__(self, boundaries, initial_position=None, speed_mps=DEFAULT_SPEED_MPS,
                 interval_seconds=DEFAULT_INTERVAL_SECONDS):

        polygons = boundaries.get('polygons', None)
        self.speed_mps = speed_mps # meters per second
        self.interval_seconds = interval_seconds # time interval between fixes

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

        # come up with a random distance based on the desired speed and interval.
        change_m = self.speed_mps * (random.random() + 0.5) * self.interval_seconds

        d = geopy.distance.VincentyDistance(meters=change_m)
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


class DemoSourcePlugin(TrackingPlugin):

    '''
    Generate track data using RandomMover.
    '''
    range_polygon = models.ForeignKey(mapping.models.PolygonFeature, null=True,
                                      on_delete=models.PROTECT)

    source_plugin_reverse_relation = 'demosourceplugin'
    source_plugins = GenericRelation(
        SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id',
        related_query_name=source_plugin_reverse_relation, related_name='+')

    def should_run(self, source_plugin):
        return True

    def fetch(self, source, cursor_data=None):

        self.logger = logging.getLogger(self.__class__.__name__)

        # create cursor_data
        self.cursor_data = copy.copy(cursor_data) if cursor_data else {}

        speed_mps = self.cursor_data.get('speed_mps', RandomMover.DEFAULT_SPEED_MPS)
        interval_seconds = self.cursor_data.get('interval_seconds', RandomMover.DEFAULT_INTERVAL_SECONDS)


        try:
            default_starttime = datetime.datetime.now(tz=pytz.utc) - timedelta(seconds=24 * interval_seconds)
            _ = self.cursor_data['latest_timestamp']
            latest_ts = parse_date(_)
            latest_ts = max(default_starttime, latest_ts)
        except KeyError:
            latest_ts = default_starttime

        self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)

        boundaries = self.cursor_data['boundaries']

        last_location = self.cursor_data.get('last_location')
        r = RandomMover(boundaries=boundaries, initial_position=last_location,
                        speed_mps=speed_mps, interval_seconds=interval_seconds)

        next_ts = latest_ts + timedelta(seconds=interval_seconds)

        now = datetime.datetime.now(tz=pytz.utc)
        # lt = latest_ts
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

            # Bump the next observation time by a random timedelta that's based on interval_seconds.
            next_ts += timedelta(seconds=random.randint(int(interval_seconds*0.9), interval_seconds))

        if observation:
            # Update cursor_data for this source.
            self.cursor_data['latest_timestamp'] = observation.recorded_at.isoformat()
            self.cursor_data['last_location'] = {'latitude': observation.latitude,
                                                       'longitude': observation.longitude
                                                       }
            self.logger.info("Saved config for collar_id %s" % (source.manufacturer_id,))

