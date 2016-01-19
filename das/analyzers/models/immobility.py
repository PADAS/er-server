import logging

from django.contrib.gis.db import models

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL

logger = logging.getLogger(__name__)


class ImmobilityAnalyzer(Analyzer):
    """ Analyzer for a Track. """

    radius = models.FloatField(default=20.0)
    speed_threshold = models.FloatField(default=10 ** -1)

    def analyze(self, track):
        """ analyze track for immobile state """

        logger.info('ImmobilityAnalyzer analyzing')

        result = AnalyzerResult()
        result.analyzer_type = self.__class__

        # assume immobile until detected otherwise
        result.level = CRITICAL

        for speed in track.speed_series():

            if speed >= self.speed_threshold:

                result.value = speed
                result.level = NOMINAL
                break

        return result
