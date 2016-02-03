from datetime import datetime

from django.test import TestCase
from django.contrib.gis.geos import Point, LineString, MultiLineString
import pytz

from analyzers.models.analyzer import NOMINAL, CRITICAL
from analyzers.models.geofence import GeofenceAnalyzer
from mapping.models import FeatureType, LineFeature
from observations.track import Track


class TestGeofenceAnalyzer(TestCase):

    def setUp(self):

        # clockwise fence around null island
        self.fence = MultiLineString(
            LineString((
                (-1, 1),
                (1, 1),
                (1, -1),
                (-1, -1),
                (-1, 1)
            ))
        )
        feature_type = FeatureType.objects.create(name='da fence')
        self.polygon_feature = LineFeature.objects.create(
            presentation={},
            feature_geometry=self.fence,
            type=feature_type
        )

        self.analyzer = GeofenceAnalyzer(fence=self.polygon_feature)

        crossing_fence_points = ((2, 0), (0, 0))
        not_crossing_fence_points = ((0, 0), (0.5, 0))

        times = [
            datetime(2000,1,1,i,0,0,tzinfo=pytz.utc)
            for i in range(2)
        ]

        self.crossing_track = Track(points=crossing_fence_points, times=times)
        self.not_crossing_track = Track(points=not_crossing_fence_points, times=times)

    def test_geofence_analyzer_crosses_fence(self):
        """
        Test a track inside the fence
        """

        analyzer_result = self.analyzer.analyze(self.crossing_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)

    def test_geofence_analyzer_not_crosses_fence(self):
        """
        Test a track outside the fence
        """

        analyzer_result = self.analyzer.analyze(self.not_crossing_track)

        expected = NOMINAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)

    def test_geofence_analyzer_crosses_default_fence(self):
        """
        Test a track crossing the default equator fence
        """

        analyzer = GeofenceAnalyzer()
        crossing_fence_points = ((0, -1), (0, 1))
        times = [
            datetime(2000,1,1,i,0,0,tzinfo=pytz.utc)
            for i in range(2)
        ]
        track = Track(points=crossing_fence_points, times=times)

        analyzer_result = analyzer.analyze(track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)
