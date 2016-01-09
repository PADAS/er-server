from django.test import TestCase

from analyzers.models.subject_analyzer import SubjectAnalyzer
from analyzers.models.geofence import GeofenceAnalyzer
from mapping.models import FeatureType, PolygonFeature
from observations.models import Subject

from django.contrib.gis.geos import Polygon, MultiPolygon


class TestSubjectAnalyzer(TestCase):

    def setUp(self):
        self.subject = Subject(name='chewbacca')
        polygon = Polygon(((0.0, 0.0), (0.0, 50.0), (50.0, 50.0), (50.0, 0.0), (0.0, 0.0)))
        dr_polygon = MultiPolygon(polygon)
        feature_type = FeatureType.objects.create(name='dr_polygon')
        polygon_feature = PolygonFeature.objects.create(
            presentation={},
            feature_geometry=dr_polygon,
            type=feature_type
        )
        self.analyzer = GeofenceAnalyzer.objects.create(polygon=polygon_feature)
        self.subject_analyzer = SubjectAnalyzer(subject=self.subject, content_object=self.analyzer)
        self.subject_analyzer.save()

    def test_subject_analyzer(self):
        actual = self.subject_analyzer.content_object
        expected = self.analyzer
        self.assertEqual(actual, expected)
