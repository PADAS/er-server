import logging

from django.contrib.gis.db import models

from .analyzer import Analyzer, AnalyzerResult

logger = logging.getLogger(__name__)


class ImmobilityAnalyzer(Analyzer):
    """ Analyzer for a Track. """

    radius = models.FloatField(default=20.0)
    speed_threshold = models.FloatField(default=10 ** -1)

    def analyze(self, track):
        """ analyze track for immobile state """

        logger.info('ImmobilityAnalyzer analyzing')

        probability = 0.0

        for speed in track.speed_series():

            if speed < self.speed_threshold:
                probability += .1

            if probability >= 1:
                break

        result = AnalyzerResult()
        result.value = probability
        result.analyzer_type = self.__class__

        return result
