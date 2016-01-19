from datetime import datetime

from django.test import TestCase
from django.contrib.gis.geos import Point, Polygon, MultiPolygon
import pytz

from analyzers.models.analyzer import NOMINAL, CRITICAL
from analyzers.models.geofence import GeofenceAnalyzer
from mapping.models import FeatureType, PolygonFeature
from observations.track import Track


class TestGeofenceAnalyzer(TestCase):

    def setUp(self):

        # clockwise fence around null island
        self.polygon = MultiPolygon(
            Polygon((
                (-1, 1),
                (1, 1),
                (1, -1),
                (-1, -1),
                (-1, 1)
            ))
        )
        feature_type = FeatureType.objects.create(name='dr_polygon')
        self.polygon_feature = PolygonFeature.objects.create(
            presentation={},
            feature_geometry=self.polygon,
            type=feature_type
        )

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

        geofence_analyzer = GeofenceAnalyzer(polygon=self.polygon_feature)
        analyzer_result = geofence_analyzer.analyze(self.inside_track)

        expected = NOMINAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)

    def test_geofence_analyzer_outside_fence(self):
        """
        Test a track outside the fence
        """

        geofence_analyzer = GeofenceAnalyzer(polygon=self.polygon_feature)
        analyzer_result = geofence_analyzer.analyze(self.outside_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected)
