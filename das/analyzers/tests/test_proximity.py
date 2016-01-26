from datetime import datetime

from django.test import TestCase
import pytz

from analyzers.models.proximity import ProximityAnalyzer
from analyzers.models.analyzer import NOMINAL, WARNING, CRITICAL
from mapping.models import FeatureType, PolygonFeature
from observations.track import Track


class TestProximityAnalyzer(TestCase):

    def setUp(self):

        inside_poly_points = [
            (0, 0),
            (0, 0),
            (0, 0),
            (0, 0),
            (0, 0),
        ]

        proximal_points = [
            (1.000001, 0),
            (1.000001, 0),
            (1.000001, 0),
            (1.000001, 0),
            (1.000001, 0),
        ]

        distal_points = [
            (100,0)
            for i in range(5)
        ]

        times = [
            datetime(2000,1,1,0,0,i,tzinfo=pytz.utc)
            for i in range(5)
        ]

        self.inside_track = Track(inside_poly_points, times)
        self.proximal_track = Track(proximal_points, times)
        self.distal_track = Track(distal_points, times)

        self.analyzer = ProximityAnalyzer()


    def test_proximity_analyzer_is_contained(self):
        """
        Test a Track inside the defined geometry
        """

        analyzer_result = self.analyzer.analyze(self.inside_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)


    def test_proximity_analyzer_is_proximal(self):
        """
        Test a Track within the distance threshold of geometry
        """

        analyzer_result = self.analyzer.analyze(self.proximal_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)

    def test_proximity_analyzer_is_distal(self):
        """
        Test a Track away from the defined geometry
        """

        analyzer_result = self.analyzer.analyze(self.distal_track)

        expected = NOMINAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)
