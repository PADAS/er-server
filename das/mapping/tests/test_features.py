import json
import logging

from faker import Faker

from django.contrib.gis.geos import Point

import mapping.views as views
from core.tests import BaseAPITest
from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType
from utils.tests_tools import is_url_resolved

logger = logging.getLogger(__name__)


# @patch("django.conf.settings.MAPPING_FEATURES_V2", True)
# @patch("das_server.settings.MAPPING_FEATURES_V2", True)
# @override_settings(MAPPING_FEATURES_V2=True)
class TestFeatures(BaseAPITest):
    fake = Faker()
    expected_features_fields = ('name', 'type', 'description', 'geojson_url')
    expected_featureset_fields = (
        'name', 'types', 'id', 'description', 'geojson_url')
    expected_fields = ('feature_type', 'description', 'pk',
                       'created_at', 'updated_at', 'external_id', 'title')

    def setUp(self):
        super().setUp()
        point = Point(-122.3286437817934, 47.58949410579475)
        self.category = DisplayCategory.objects.create(name=self.fake.name())
        self.feature_class = SpatialFeatureType.objects.create(name=self.fake.name(),
                                                               display_category=self.category)
        self.feature = SpatialFeature.objects.create(name=self.fake.name(),
                                                     feature_type=self.feature_class, feature_geometry=point)

    def test_get_features(self):
        request = self.factory.get(self.api_base + '/features/')
        assert is_url_resolved(request.path, views.FeatureListJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureListJsonView.as_view()(request)
        self.assertContains(response, 'features')

        data = json.loads(response.content)
        self.assertGreater(len(data['features']), 0)
        feature = data['features'][0]
        for field in self.expected_features_fields:
            self.assertIn(field, feature)

    def test_get_feature(self):
        request = self.factory.get(self.api_base + '/feature/')
        assert is_url_resolved(
            f"{request.path}{str(self.feature.id)}/", views.FeatureGeoJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request,
                                                      id=str(self.feature.id))
        self.assertContains(response, 'features')

        data = json.loads(response.content)
        self.assertGreater(len(data['features']), 0)
        feature = data['features'][0]['properties']
        for field in self.expected_fields:
            self.assertIn(field, feature)

    def test_get_featureset(self):
        request = self.factory.get(self.api_base + '/featureset/')
        assert is_url_resolved(request.path, views.FeatureSetListJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        self.assertContains(response, 'features')

        data = json.loads(response.content)
        self.assertGreater(len(data['features']), 0)
        feature = data['features'][0]
        for field in self.expected_featureset_fields:
            self.assertIn(field, feature)

    def test_get_featureset_single(self):
        request = self.factory.get(self.api_base + '/featureset/')
        assert is_url_resolved(
            f"{request.path}{str(self.category.id)}/", views.FeatureSetGeoJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(
            request, id=str(self.category.id))
        self.assertContains(response, 'features')

        data = json.loads(response.content)
        self.assertGreater(len(data['features']), 0)
        feature = data['features'][0]['properties']
        for field in self.expected_fields:
            self.assertIn(field, feature)

    def test_with_feature_class_is_visible_false(self):
        self.feature_class.is_visible = False
        self.feature_class.save()

        request = self.factory.get(self.api_base + '/features/')
        self.force_authenticate(request, self.app_user)
        response = views.FeatureListJsonView.as_view()(request)
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features']), 0)

        request = self.factory.get(self.api_base + '/feature/')
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request, id=str(self.feature.id))
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features']), 0)

        request = self.factory.get(self.api_base + '/featuresets/')
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        # print(response.content)
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features'][0]['types']), 0)

        request = self.factory.get(self.api_base + '/featureset/')
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(
            request, id=str(self.category.id))
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features']), 0)

    def test_with_feature_class_is_visible_false_include_hidden_true(self):
        self.feature_class.is_visible = False
        self.feature_class.save()

        request = self.factory.get(
            self.api_base + '/features/', {'include_hidden': True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureListJsonView.as_view()(request)
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features']), 1)

        request = self.factory.get(
            self.api_base + '/feature/', {'include_hidden': True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request, id=str(self.feature.id))
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features']), 1)

        request = self.factory.get(
            self.api_base + '/featuresets/', {'include_hidden': True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        # print(response.content)
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features'][0]['types']), 1)

        request = self.factory.get(
            self.api_base + '/featureset/', {'include_hidden': True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(
            request, id=str(self.category.id))
        self.assertIsNotNone(response)
        self.assertContains(response, 'features')
        data = json.loads(response.content)
        self.assertEqual(len(data['features']), 1)

    def test_get_spatialfeaturegroup(self):
        pass

    def test_get_spatialfeature(self):
        pass
