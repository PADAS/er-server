import datetime

from geopy.distance import distance
import pytz

from .analyzer import Analyzer, AnalyzerResult


class GeofenceAnalyzer(Analyzer):
    """ Analyzer for Track for Geofence boundary cross """

    min_time = datetime.time(0, tzinfo=pytz.utc)
    max_time = datetime.time.max.replace(tzinfo=pytz.utc)

    def __init__(self, polygon, buffer=None, valid_times=(min_time, max_time)):
        """ initialize with parameters

        valid_times - range of datetime.time objects in which this analysis is valid
        radius - radius in meters of cluster
        speed_threshold - speed in m/s below which immobility is assumed
        """
        self.valid_times = valid_times
        self.buffer = buffer
        self.polygon = polygon

    def distance_to_exterior_point(self, point):
        """ for a point outside self.polygon, return the distance in meters
        to that point """
        d = self.polygon.boundary.project(point)
        p = self.polygon.boundary.interpolate(d)
        return distance(p.coords, point.coords).m

    def analyze(self, track):
        """ analyze track """

        return_value = 0.0

        point = track[-1]

        if self.polygon.contains(point):
            # contained, calculate distance to polygon
            pass
        else:

            # outside the fence, calculate distance to polygon
            distance = self.distance_to_exterior_point(point)
            # do something with that
            return_value = 1

        result = AnalyzerResult()
        result.value = return_value
        result.analyzer_type = self.__class__

        return result
