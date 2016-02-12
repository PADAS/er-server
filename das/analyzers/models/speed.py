import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point as DjangoPoint

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL
from ..exceptions import InsufficientDataAnalyzerException

logger = logging.getLogger(__name__)


class SpeedAnalyzer(Analyzer):
    """ Speed Analyzer for a Track. """

    max_speed = models.FloatField(default=2)
    min_speed = models.FloatField(default=0)

    def analyze(self, track):
        """ analyze track for speed thresholds. Only the 24 hours before the most
        recent observation are considered """
        super().analyze(track)

        if len(track) < 5:
            raise InsufficientDataAnalyzerException

        result = AnalyzerResult()
        result.analyzer_type = self.__class__.__name__

        track = track.truncate(hours=24)

        for i, speed in enumerate(track.speed_series()):

            if (speed <= self.min_speed) or (speed >= self.max_speed):

                result.value = speed
                result.level = CRITICAL

                # have to translate shapely Point to a DjangoPoint for SpatialProxy
                point = track.geo_series[i]
                result.location = DjangoPoint(point.x, point.y)
                logger.info('Speed Analyzer detected speed outside of window [{}-{}] m/s'.format(self.min_speed, self.max_speed))

                break

        return result
