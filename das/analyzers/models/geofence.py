import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon, MultiPolygon

from geopy.distance import distance

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL

from mapping.models import FeatureType, PolygonFeature

logger = logging.getLogger(__name__)


class GeofenceAnalyzer(Analyzer):
    """ Analyzer for Track for Geofence boundary cross """

    polygon = models.ForeignKey(to=PolygonFeature)
    interior_buffer = models.FloatField(default=0.0)

    # default box around africa
    _default_polygon = MultiPolygon(
        Polygon((
            (-20, 40),
            (60, 40),
            (60, -40),
            (-20, -40),
            (-20, 40)
        ))
    )

    @property
    def polygon_or_default(self):
        try:
            return self.polygon
        except:
            # create the objects, but we don't need to save() them
            feature_type = FeatureType(name='')

            poly = PolygonFeature(
                presentation={},
                feature_geometry=self._default_polygon,
                type=feature_type
            )
            return poly

    def distance_to_exterior_point(self, point):
        """ for a point outside self.polygon, return the distance in meters
        to that point """
        d = self.polygon.feature_geometry.boundary.project(point)
        p = self.polygon.feature_geometry.boundary.interpolate(d)
        return distance(p.coords, point.coords).m

    def analyze(self, track):
        """ analyze track for geofence containment """

        super().analyze(track)

        point = track[-1]

        polygon = self.polygon_or_default

        result = AnalyzerResult()
        result.analyzer_type = self.__class__
        result.level = NOMINAL

        if polygon.feature_geometry.contains(Point(point.x, point.y)):
            # contained, calculate distance to polygon
            logger.debug('GeofenceAnalyzer: last point of track contained within polygon')
        else:

            # outside the fence, calculate distance to polygon
            distance = self.distance_to_exterior_point(Point(point.x, point.y))
            # do something with that
            result.value = distance
            result.level = CRITICAL
            logger.debug('GeofenceAnalyzer: last point of track not contained within polygon')

        return result
