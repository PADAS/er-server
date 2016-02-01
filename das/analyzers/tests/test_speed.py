from datetime import datetime

from django.test import TestCase
import pytz

from analyzers.models.speed import SpeedAnalyzer
from analyzers.models.analyzer import NOMINAL, WARNING, CRITICAL
from observations.track import Track


class TestSpeedAnalyzer(TestCase):

    def setUp(self):

        slow_points = [
            (0, 0),
            (0, 0),
            (0, 0),
            (0, 0),
            (0, 0),
        ]

        fast_points = [
            (1, 0),
            (2, 0),
            (3, 0),
            (4, 0),
            (5, 0),
        ]

        # roughly 1m/s travel along the equator
        just_right_points = [
            (1*10**-5, 0),
            (2*10**-5, 0),
            (3*10**-5, 0),
            (4*10**-5, 0),
            (5*10**-5, 0),
        ]

        times = [
            datetime(2000,1,1,0,0,i,tzinfo=pytz.utc)
            for i in range(5)
        ]

        self.slow_track = Track(slow_points, times)
        self.fast_track = Track(fast_points, times)
        self.just_right_track = Track(just_right_points, times)

        self.analyzer = SpeedAnalyzer(max_speed=100, min_speed=0)


    def test_speed_analyzer_warns_too_fast(self):
        """
        Test a Track inside the defined geometry
        """

        analyzer_result = self.analyzer.analyze(self.fast_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)


    def test_speed_analyzer_warns_too_slow(self):
        """
        Test a Track within the distance threshold of geometry
        """

        analyzer_result = self.analyzer.analyze(self.slow_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)

    def test_speed_analyzer_within_bounds(self):
        """
        Test a Track away from the defined geometry
        """

        analyzer_result = self.analyzer.analyze(self.just_right_track)

        expected = NOMINAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)
