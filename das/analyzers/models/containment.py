import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon, MultiPolygon
from django.core.exceptions import ObjectDoesNotExist

from activity.models import Event
from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL
from .utils import distance_to_exterior_point
from mapping.models import FeatureType, PolygonFeature

logger = logging.getLogger(__name__)


class ContainmentAnalyzer(Analyzer):
    """ Analyzer for Track for polygon boundary crossing """

    event_type = Event.ET_ANALYZER

    polygon = models.ForeignKey(
        to=PolygonFeature,
        on_delete=models.CASCADE,
        null=True
    )

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
        """ analyze track for geofence containment. Only the most recent
        observation is considered """

        super().analyze(track)

        point = track[-1]

        polygon = self.polygon_or_default

        result = AnalyzerResult(self)
        result.analyzer_type = self.__class__.__name__
        result.level = NOMINAL
        result.location = point

        if polygon.feature_geometry.contains(Point(point.x, point.y)):
            result.title = 'Contained within polygon'
            logger.debug(result.title)
        else:

            # outside the fence, calculate distance to polygon
            distance = distance_to_exterior_point(polygon.feature_geometry, Point(point.x, point.y))
            result.value = distance
            result.level = CRITICAL
            result.title = 'Not contained within polygon'
            logger.debug(result.title)

        return result
