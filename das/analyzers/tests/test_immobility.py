from datetime import datetime

from django.test import TestCase
import pytz

from analyzers.models.immobility import ImmobilityAnalyzer
from observations.track import Track


class TestImmobilityAnalyzer(TestCase):

    # fixtures = ['observations_source.json']

    def setUp(self):

        # ~1 m/s stroll along the equator
        mobile_points = [
            (i * 10 ** -6,0)
            for i in range(5)
        ]

        # dead track
        immobile_points = [
            (0,0)
            for i in range(5)
        ]

        times = [
            datetime(2000,1,1,0,0,i,tzinfo=pytz.utc)
            for i in range(5)
        ]

        self.mobile_track = Track(mobile_points, times)
        self.immobile_track = Track(immobile_points, times)

    def test_immobility_analyzer_is_mobile(self):
        """
        Test a mobile Track
        """

        analyzer = ImmobilityAnalyzer()
        analyzer_result = analyzer.analyze(self.mobile_track)

        expected = 0.0
        actual = analyzer_result.value

        self.assertAlmostEqual(actual, expected)

    def test_immobility_analyzer_is_immobile(self):
        """
        Test an immobile Track
        """

        analyzer = ImmobilityAnalyzer()
        analyzer_result = analyzer.analyze(self.immobile_track)

        expected = 0.1
        actual = analyzer_result.value

        self.assertGreater(actual, expected)
