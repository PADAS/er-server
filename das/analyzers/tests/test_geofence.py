from datetime import datetime

from django.test import TestCase
import pytz
from shapely.geometry import Point, Polygon

from analyzers.geofence import GeofenceAnalyzer
from observations.track import Track


class TestGeofenceAnalyzer(TestCase):

    def setUp(self):

        # clockwise fence around null island
        self.polygon = Polygon((
            (-1, 1),
            (1, 1),
            (1, -1),
            (-1, -1),
            (-1, 1)
        ))

        inside_fence_points = [Point((0, 0))]

        outside_fence_points = [Point((2, 0))]

        times = [
            datetime(2000,1,1,0,0,i,tzinfo=pytz.utc)
            for i in range(1)
        ]

        self.inside_track = Track(inside_fence_points, times)
        self.outside_track = Track(outside_fence_points, times)

    def test_geofence_analyzer_inside_fence(self):
        """
        Test a track inside the fence
        """

        analyzer = GeofenceAnalyzer(self.polygon)
        analyzer_result = analyzer.analyze(self.inside_track)

        expected = 0.0
        actual = analyzer_result.value

        self.assertEqual(actual, expected)

    def test_geofence_analyzer_outside_fence(self):
        """
        Test a track outside the fence
        """

        analyzer = GeofenceAnalyzer(self.polygon)
        analyzer_result = analyzer.analyze(self.outside_track)

        expected = 1.0
        actual = analyzer_result.value

        self.assertEqual(actual, expected)
