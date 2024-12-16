import json
import logging

import pytest
from faker import Faker

from django.contrib.gis.geos import LineString, MultiLineString, MultiPoint, Point
from django.urls import reverse

import mapping.views as views
from analyzers.forms import FeatureProximityAnalyzerForm, GeofenceSubjectAnalyzerForm
from core.tests import BaseAPITest
from factories import SpatialFeatureFactory, SpatialFeatureGroupStaticFactory
from mapping.models import (
    DisplayCategory,
    SpatialFeature,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
)
from utils.tests_tools import is_url_resolved

logger = logging.getLogger(__name__)


# @patch("django.conf.settings.MAPPING_FEATURES_V2", True)
# @patch("das_server.settings.MAPPING_FEATURES_V2", True)
# @override_settings(MAPPING_FEATURES_V2=True)
class TestFeatures(BaseAPITest):
    fake = Faker()
    expected_features_fields = ("name", "type", "description", "geojson_url")
    expected_featureset_fields = ("name", "types", "id", "description", "geojson_url")
    expected_fields = ("feature_type", "description", "pk", "created_at", "updated_at", "external_id", "title")

    def setUp(self):
        super().setUp()
        point = Point(-122.3286437817934, 47.58949410579475)
        self.category = DisplayCategory.objects.create(name=self.fake.name())
        self.feature_class = SpatialFeatureType.objects.create(name=self.fake.name(), display_category=self.category)
        self.feature = SpatialFeature.objects.create(
            name=self.fake.name(), feature_type=self.feature_class, feature_geometry=point
        )

    def test_get_features(self):
        request = self.factory.get(self.api_base + "/features/")
        assert is_url_resolved(request.path, views.FeatureListJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureListJsonView.as_view()(request)
        self.assertContains(response, "features")

        data = json.loads(response.content)
        self.assertGreater(len(data["features"]), 0)
        feature = data["features"][0]
        for field in self.expected_features_fields:
            self.assertIn(field, feature)

    def test_get_feature(self):
        request = self.factory.get(self.api_base + "/feature/")
        assert is_url_resolved(f"{request.path}{str(self.feature.id)}/", views.FeatureGeoJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request, id=str(self.feature.id))
        self.assertContains(response, "features")

        data = json.loads(response.content)
        self.assertGreater(len(data["features"]), 0)
        feature = data["features"][0]["properties"]
        for field in self.expected_fields:
            self.assertIn(field, feature)

    def test_get_featureset(self):
        request = self.factory.get(self.api_base + "/featureset/")
        assert is_url_resolved(request.path, views.FeatureSetListJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        self.assertContains(response, "features")

        data = json.loads(response.content)
        self.assertGreater(len(data["features"]), 0)
        feature = data["features"][0]
        for field in self.expected_featureset_fields:
            self.assertIn(field, feature)

    def test_get_featureset_single(self):
        request = self.factory.get(self.api_base + "/featureset/")
        assert is_url_resolved(f"{request.path}{str(self.category.id)}/", views.FeatureSetGeoJsonView)
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(request, id=str(self.category.id))
        self.assertContains(response, "features")

        data = json.loads(response.content)
        self.assertGreater(len(data["features"]), 0)
        feature = data["features"][0]["properties"]
        for field in self.expected_fields:
            self.assertIn(field, feature)

    def test_with_feature_class_is_visible_false(self):
        self.feature_class.is_visible = False
        self.feature_class.save()

        request = self.factory.get(self.api_base + "/features/")
        self.force_authenticate(request, self.app_user)
        response = views.FeatureListJsonView.as_view()(request)
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"]), 0)

        request = self.factory.get(self.api_base + "/feature/")
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request, id=str(self.feature.id))
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"]), 0)

        request = self.factory.get(self.api_base + "/featuresets/")
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        # print(response.content)
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"][0]["types"]), 0)

        request = self.factory.get(self.api_base + "/featureset/")
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(request, id=str(self.category.id))
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"]), 0)

    def test_with_feature_class_is_visible_false_include_hidden_true(self):
        self.feature_class.is_visible = False
        self.feature_class.save()

        request = self.factory.get(self.api_base + "/features/", {"include_hidden": True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureListJsonView.as_view()(request)
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"]), 1)

        request = self.factory.get(self.api_base + "/feature/", {"include_hidden": True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureGeoJsonView.as_view()(request, id=str(self.feature.id))
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"]), 1)

        request = self.factory.get(self.api_base + "/featuresets/", {"include_hidden": True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetListJsonView.as_view()(request)
        # print(response.content)
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"][0]["types"]), 1)

        request = self.factory.get(self.api_base + "/featureset/", {"include_hidden": True})
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(request, id=str(self.category.id))
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertEqual(len(data["features"]), 1)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureGroup:
    fake = Faker()

    @pytest.fixture()
    def spatial_feature_group_mixed_geometry(self):
        features = [
            SpatialFeatureFactory(
                name=self.fake.name(), feature_geometry=MultiPoint(Point(-122.3286437817934, 47.58949410579475))
            ),
            SpatialFeatureFactory(
                name=self.fake.name(), feature_geometry=MultiPoint(Point(-122.3286437817934, 47.58949410579475))
            ),
            SpatialFeatureFactory(
                name=self.fake.name(),
                feature_geometry=MultiLineString(
                    LineString((-122.3286437817934, 47.58949410579475), (-122.3286437817934, 47.58949410579475))
                ),
            ),
        ]
        sfgs = SpatialFeatureGroupStaticFactory(name=self.fake.name())
        sfgs.features.add(*features)
        return sfgs

    @pytest.fixture()
    def spatial_feature_group_linestring_only(self):
        features = [
            SpatialFeatureFactory(
                name=self.fake.name(),
                feature_geometry=MultiLineString(
                    LineString((-122.3286437817934, 47.58949410579475), (-122.3286437817934, 47.58949410579475))
                ),
            )
        ]
        sfgs = SpatialFeatureGroupStaticFactory(name=self.fake.name())
        sfgs.features.add(*features)
        return sfgs

    def test_spaitalfeaturegroupstatic_include_linestring_groups(self, spatial_feature_group_linestring_only):
        assert SpatialFeatureGroupStatic.objects.exists()
        groups = SpatialFeatureGroupStatic.objects.by_spatial_type("MULTILINESTRING")
        assert groups.count() == 1
        assert spatial_feature_group_linestring_only == groups.first()

    def test_spatialfeaturegroupstatic_filter_out_mixed_or_non_linestring_groups(
        self, spatial_feature_group_mixed_geometry
    ):
        assert SpatialFeatureGroupStatic.objects.exists()
        groups = SpatialFeatureGroupStatic.objects.by_spatial_type("MULTILINESTRING")
        assert spatial_feature_group_mixed_geometry not in groups

    def test_geofencesubjectanalyzerform_is_invalid_when_a_non_linestring_in_critical_geofence_group(
        self, spatial_feature_group_mixed_geometry, spatial_feature_group_linestring_only, django_assert_num_queries
    ):
        with django_assert_num_queries(3):
            form = GeofenceSubjectAnalyzerForm(
                {
                    "critical_geofence_group": spatial_feature_group_mixed_geometry.pk,
                    "warning_geofence_group": spatial_feature_group_mixed_geometry.pk,
                    "containment_regions": spatial_feature_group_linestring_only.pk,
                }
            )
            assert not form.is_valid()
            assert set(["critical_geofence_group", "warning_geofence_group", "containment_regions"]).issubset(
                form.errors.keys()
            )

    def test_featureproximityanalyzerform_is_invalid_when_a_non_multipoint_in_proximal_features(
        self, spatial_feature_group_linestring_only, django_assert_num_queries
    ):
        with django_assert_num_queries(1):
            form = FeatureProximityAnalyzerForm({"proximal_features": spatial_feature_group_linestring_only.pk})
            assert not form.is_valid()
            assert "proximal_features" in form.errors.keys()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureListView:
    @pytest.fixture
    def category1(self):
        return DisplayCategory.objects.create(name="Category One")

    @pytest.fixture
    def category2(self):
        return DisplayCategory.objects.create(name="Category Two")

    @pytest.fixture
    def feature_type1(self, category1):
        return SpatialFeatureType.objects.create(name="Type One", display_category=category1)

    @pytest.fixture
    def feature_type2(self, category2):
        return SpatialFeatureType.objects.create(name="Type Two", display_category=category2)

    @pytest.fixture
    def feature1(self, feature_type1):
        return SpatialFeature.objects.create(
            name="Feature One", feature_type=feature_type1, feature_geometry=Point(-122.1, 47.5)
        )

    @pytest.fixture
    def feature2(self, feature_type1):
        return SpatialFeature.objects.create(
            name="Feature Two", feature_type=feature_type1, feature_geometry=Point(-122.2, 47.6)
        )

    @pytest.fixture
    def feature3(self, feature_type2):
        return SpatialFeature.objects.create(
            name="Feature Three", feature_type=feature_type2, feature_geometry=Point(-122.3, 47.7)
        )

    def test_list_all_features(self, user_client, feature1, feature2, feature3):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, dict)
        assert "data" in data
        data = data["data"]
        assert len(data) == 3

        # Check structure of first feature
        feature = data[0]
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature
        expected_properties = [
            "id",
            "name",
            "feature_type_id",
            "feature_type_name",
            "feature_set_id",
            "feature_set_name",
            "description",
            "short_name",
        ]
        for prop in expected_properties:
            assert prop in feature["properties"]

    def test_filter_by_feature_type(self, user_client, feature1, feature2, feature3, feature_type1):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_type": str(feature_type1.id)})
        assert response.status_code == 200
        data = response.json()
        data = data["data"]

        # Only feature1 and feature2 belong to feature_type1
        assert len(data) == 2
        names = [f["properties"]["name"] for f in data]
        assert "Feature One" in names
        assert "Feature Two" in names

    def test_filter_by_feature_set(self, user_client, feature1, feature2, feature3, category2):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_set": str(category2.id)})
        assert response.status_code == 200
        data = response.json()
        data = data["data"]

        # Only feature3 belongs to category2
        assert len(data) == 1
        assert data[0]["properties"]["name"] == "Feature Three"

    def test_filter_by_feature_set_and_feature_type_error(self, user_client, category1, feature_type1):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_set": str(category1.id), "feature_type": str(feature_type1.id)})
        assert response.status_code == 400
        data = response.json()
        assert "status" in data
        assert "detail" in data["status"]
        assert "You can't filter by both feature_set and feature_type" in data["status"]["detail"]
