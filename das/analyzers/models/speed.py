import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point as DjangoPoint

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL

logger = logging.getLogger(__name__)


class SpeedAnalyzer(Analyzer):
    """ Speed Analyzer for a Track. """

    max_speed = models.FloatField(default=2)
    min_speed = models.FloatField(default=0)

    def analyze(self, track):
        """ analyze track for speed thresholds. Only the 24 hours before the most
        recent observation are considered """
        super().analyze(track)

        result = AnalyzerResult()
        result.analyzer_type = self.__class__.__name__

        track = self.truncate_track(track, hours=24)

        time_series = track.speed_series()

        for i, speed in enumerate(track.speed_series()):

            if speed >= self.max_speed:

                result.value = speed
                result.level = CRITICAL
                break

            if speed <= self.min_speed:

                result.value = speed
                result.level = CRITICAL

                # have to translate shapely Point to a DjangoPoint so SpatialProxy
                # doesn't throw a wobbly
                point = track.geo_series[i]
                result.location = DjangoPoint(point.x, point.y)

                break

        if result.level > NOMINAL:
            logger.info('Speed Analyzer detected exceeded speed threshold')

        return result
