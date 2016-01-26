import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon, MultiPolygon

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL
from .utils import distance_to_exterior_point
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


    def analyze(self, track):
        """ analyze track for geofence containment. Only the most recent
        observation is considered """

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
            distance = distance_to_exterior_point(polygon.feature_geometry, Point(point.x, point.y))
            result.value = distance
            result.level = CRITICAL
            result.location = point
            logger.debug('GeofenceAnalyzer: last point of track not contained within polygon')

        return result
