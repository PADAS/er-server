import datetime

import pytz

from .analyzer import Analyzer, AnalyzerResult


class ImmobilityAnalyzer(Analyzer):
    """ Analyzer for a Track. """

    min_time = datetime.time(0, tzinfo=pytz.utc)
    max_time = datetime.time.max.replace(tzinfo=pytz.utc)

    def __init__(self, valid_times=(min_time, max_time), radius=20, speed_threshold=(10 ** -1)):
        """ initialize with parameters

        valid_times - range of datetime.time objects in which this analysis is valid
        radius - radius in meters of cluster
        speed_threshold - speed in m/s below which immobility is assumed
        """
        self.valid_times = valid_times
        self.radius = radius
        self.speed_threshold = speed_threshold

    def analyze(self, track):
        """ analyze track """

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
