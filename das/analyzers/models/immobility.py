from datetime import timedelta
import logging

from django.contrib.gis.db import models

from .analyzer import Analyzer, AnalyzerResult, NOMINAL, CRITICAL

logger = logging.getLogger(__name__)


class ImmobilityAnalyzer(Analyzer):
    """ Analyzer for a Track. """

    radius = models.FloatField(default=20.0)
    speed_threshold = models.FloatField(default=10 ** -1)

    def analyze(self, track):
        """ analyze track for immobile state. Only the 24 hours before the most
        recent observation are considered """

        super().analyze(track)

        result = AnalyzerResult()
        result.analyzer_type = self.__class__.__name__

        # assume immobile until detected otherwise
        result.level = CRITICAL

        # truncate track to recent observations
        t_last_observation, p_last_observation  = track.last_observation
        t_cutoff = t_last_observation - timedelta(hours=24)
        track = track.truncate(before=t_cutoff)

        time_series = track.speed_series()

        for speed in track.speed_series():

            if speed >= self.speed_threshold:

                result.value = speed
                result.level = NOMINAL
                break

        if result.level > NOMINAL:
            logger.info('Immobility Analyzer detected immobile track')

        return result
