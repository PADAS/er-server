import logging
import json

from django.contrib.gis.geos import Point
from faker import Faker

from core.tests import BaseAPITest
from mapping.models import SpatialFeature, SpatialFeatureType, DisplayCategory
import mapping.views as views

logger = logging.getLogger(__name__)


class TestFeatures(BaseAPITest):
    fake = Faker()
    expected_features_fields = ('name', 'type', 'description', 'geojson_url')
    expected_fields = ('name', 'type', 'description', 'pk', 'created_at', 'updated_at', 'fields', 'external_id', 'featureset',
                       'title')

    def setUp(self):
        super().setUp()
        point = Point(-122.3286437817934, 47.58949410579475)
        category = DisplayCategory.objects.create(name=self.fake.name())
        self.feature_class = SpatialFeatureType.objects.create(name=self.fake.name(),
                                                               display_category=category)
        self.feature = SpatialFeature.objects.create(name=self.fake.name(),
                                                     feature_type=self.feature_class, feature_geometry=point)
        self.feature_noname = SpatialFeature.objects.create(feature_type=self.feature_class,
                                                            feature_geometry=point)

    def test_get_features(self):
        request = self.factory.get(self.api_base + '/features/')
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
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        self.assertContains(response, 'features')

        data = json.loads(response.content)
        self.assertGreater(len(data['features']), 0)
        feature = data['features'][0]
        for field in self.expected_features_fields:
            self.assertIn(field, feature)

    def test_get_featureset_single(self):
        request = self.factory.get(self.api_base + '/featureset/')
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request,
                                                      id=str(self.feature_class))
        self.assertContains(response, 'features')

        data = json.loads(response.content)
        self.assertGreater(len(data['features']), 0)
        feature = data['features'][0]['properties']
        for field in self.expected_fields:
            self.assertIn(field, feature)

    def test_get_spatialfeaturegroup(self):
        pass

    def test_get_spatialfeature(self):
        pass
