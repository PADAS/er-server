import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point as DjangoPoint

from activity.models import Event
from .analyzer import Analyzer, AnalyzerResult, CRITICAL
from ..exceptions import InsufficientDataAnalyzerException

logger = logging.getLogger(__name__)


class SpeedAnalyzer(Analyzer):
    """ Speed Analyzer for a Track. """

    event_type = Event.ET_SPEED

    max_speed = models.FloatField(default=2)
    min_speed = models.FloatField(default=0)

    def analyze(self, track):
        """ analyze track for speed thresholds. Only the 24 hours before the most
        recent observation are considered """
        super().analyze(track)

        if len(track) < 3:
            raise InsufficientDataAnalyzerException

        result = AnalyzerResult(self)
        result.analyzer_type = self.name

        speed = track.speed_series[-1]

        result.value = speed
        point = track.geo_series[-1]
        result.location = DjangoPoint(point.x, point.y)

        if (speed <= self.min_speed) or (speed >= self.max_speed):

            result.level = CRITICAL
            result.title = "Speed is outside of [{}-{}] m/s".format(self.min_speed, self.max_speed)
            logger.info(result.title)
        else:
            result.title = "Speed is within range [{}-{}] m/s".format(self.min_speed, self.max_speed)


        return result
