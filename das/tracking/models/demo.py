from django.contrib.gis.geos import Polygon, Point, MultiPolygon
import random

import geopy
import geopy.distance

from data_input.models import PluginConfSource


from functools import namedtuple

from tracking.models.plugin_base import Obs
from .plugin_base import Plugin
import datetime
from datetime import timedelta

from dateutil.parser import parse as parse_date
import pytz

import logging
from django.contrib.gis.db import models

import mapping.models

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

        change_k = random.random() * 3.0
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


class DemoSubjectPlugin(Plugin):

    '''
    Generate track data using RandomMover.
    '''
    DEFAULT_START_OFFSET = timedelta(days=14)

    # service_user_id = models.CharField(max_length=50,
    #                                    help_text='The username for querying the Savannah Tracking service.')
    # service_password = models.CharField(max_length=50,
    #                                     help_text='The password for querying the Savannah Tracking service.')
    # service_api_host = models.CharField(max_length=50,
    #                                     help_text='the ip-address or host-name for the Savannah Tracking service.')

    range_polygon = models.ForeignKey(mapping.models.PolygonFeature, null=True)


    def fetch(self, source_plugin):

        self.logger = logging.getLogger(self.__class__.__name__)

        source = source_plugin.source
        self.cursor_data = source_plugin.cursor_data or {}
        try:
            default_starttime = datetime.datetime.now(tz=pytz.utc) - self.DEFAULT_START_OFFSET
            _ = self.cursor_data.get('latest_timestamp', None)
            latest_ts = parse_date(_)
            latest_ts = max(default_starttime, latest_ts)

        except AttributeError:
            latest_ts = default_starttime

        self.logger.debug('Fetching data for collar_id %s', source.manufacturer_id)

        boundaries = self.cursor_data['boundaries']

        last_location = self.cursor_data.get('last_location')
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
            notify = True

        if observation:
            # Save 'cursor' info for this source.
            self.cursor_data['latest_timestamp'] = observation.recorded_at.isoformat()
            self.cursor_data['last_location'] = {'latitude': observation.latitude,
                                                       'longitude': observation.longitude
                                                       }
            self.logger.info("Saved config for collar_id %s" % (source.manufacturer_id,))

