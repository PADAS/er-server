from datetime import timedelta
import operator

from fiona import crs
import geopandas as gpd
from geopy.distance import distance
import numpy as np
import pandas as pd
from shapely.geometry import Point, LineString

import itertools


class Track():
    """ defines a track consisting of points identified by location in time and space """

    def __init__(self, points=None, times=None):
        """ parameters should be sequences of equal length:
        points - sequence of points, any type which can be handled by shapely.geometry.Point
        times - sequence of aware datetimes
        """
        if points and times:
            self.geo_series = gpd.GeoSeries([Point(p) for p in points], index=times)
            self.geo_series.crs = crs.from_epsg(4326)

    def __getitem__(self, index):
        return self.geo_series[index]

    def __len__(self):
        return len(self.geo_series)

    @classmethod
    def from_observations(cls, observations):
        """ Create a Track from a sequence of Observations """
        sorted_observations = sorted(observations, key=operator.attrgetter('recorded_at'))
        points = [(o.location.coords, o.recorded_at) for o in sorted_observations if o.location and o.recorded_at]
        if points:
            return cls(*(zip(*points)))

    def as_linestring(self):
        return gpd.GeoSeries([LineString(self.geo_series[:])])

    @property
    def last_observation(self):
        """ returns (timestamp, Point) of last observation """
        return (self.geo_series.index[-1], self.geo_series[-1])

    @property
    def points(self):
        return self.geo_series[:]

    @property
    def times(self):
        return self.geo_series.index

    def truncate(self, hours=None, before=None):
        """ returns a new Track with some records removed
        @optional_parameters

        before: dates before this are removed
        hours: only the most recent hours hours are preserved
        """

        track = Track()

        if hours:
            t_last_observation, _  = self.last_observation
            before = t_last_observation - timedelta(hours=hours)

        if before:
            track.geo_series = self.geo_series[self.geo_series.index >= before]

        return track

    @property
    def speed_series(self):

        def speed_gen():
            for i in range(1, len(self.geo_series)):
                p0 = self.geo_series[i - 1]
                p1 = self.geo_series[i]

                t0 = self.geo_series.index[i - 1]
                t1 = self.geo_series.index[i]

                dist_meters = distance((p1.y, p1.x), (p0.y, p0.x)).m
                dt = abs((t1 - t0).total_seconds())
                yield dist_meters / dt

        speeds = itertools.chain((np.nan,), speed_gen())

        # FIXME: get Series to init from a generator
        return pd.Series(list(speeds), index=self.geo_series.index)
