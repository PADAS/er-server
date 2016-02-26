import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon, MultiPolygon
from django.core.exceptions import ObjectDoesNotExist

from activity.models import Event
from .analyzer import Analyzer, AnalyzerResult, CRITICAL
from .utils import distance_to_exterior_point
from mapping.models import FeatureType, PolygonFeature

logger = logging.getLogger(__name__)


class ProximityAnalyzer(Analyzer):
    """ Speed Analyzer for a Track. """

    event_type = Event.ET_PROXIMITY

    polygon = models.ForeignKey(
        to=PolygonFeature,
        on_delete=models.CASCADE,
        null=True
    )

    distance_m = models.FloatField(default=100)  # in meters

    # default box around null island
    _default_polygon = MultiPolygon(
        Polygon((
            (-1, 1),
            (1, 1),
            (1, -1),
            (-1, -1),
            (-1, 1)
        ))
    )

    @property
    def polygon_or_default(self):
        if self.polygon:
            return self.polygon

        else:
            # create the objects, but we don't need to save() them
            feature_type = FeatureType(name='')

            poly = PolygonFeature(
                presentation={},
                feature_geometry=self._default_polygon,
                type=feature_type
            )
            return poly

    def analyze(self, track):
        """ analyze track for proximity conditions. Only the most
        recent observation is considered """

        super().analyze(track)

        result = AnalyzerResult(self)
        result.analyzer_type = self.__class__.__name__

        poly = self.polygon_or_default
        point = track[-1]

        if poly.feature_geometry.contains(Point(point.x, point.y)):
            distance = 0.0
        else:
            distance = distance_to_exterior_point(poly.feature_geometry, Point(point.x, point.y))

        result.location = Point(point.x, point.y)

        if distance <= self.distance_m:
            result.value = distance
            result.level = CRITICAL
            result.title = 'Proximity Urgent'
            logger.info(result.title)
        else:
            result.title = 'Proximity OK'
            logger.info(result.title)

        return result
