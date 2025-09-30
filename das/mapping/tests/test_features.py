import json
import logging

import pytest
from faker import Faker

from django.contrib.gis import geos
from django.contrib.gis.geos import LineString, MultiLineString, MultiPoint, Point
from django.urls import reverse

import mapping.views as views
from analyzers.forms import GeofenceSubjectAnalyzerForm
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


# Shared fixtures for mapping tests
@pytest.fixture
def category1():
    return DisplayCategory.objects.create(name="Category One")


@pytest.fixture
def category2():
    return DisplayCategory.objects.create(name="Category Two")


@pytest.fixture
def feature_type1(category1):
    return SpatialFeatureType.objects.create(name="Type One", display_category=category1)


@pytest.fixture
def feature_type2(category2):
    return SpatialFeatureType.objects.create(name="Type Two", display_category=category2)


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
        assert is_url_resolved(f"{request.path}{self.feature.id}/", views.FeatureGeoJsonView)
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
        assert is_url_resolved(f"{request.path}{self.category.id}/", views.FeatureSetGeoJsonView)
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

        # Test that content-length header matches actual content length
        content_length = response.get("Content-Length")
        self.assertIsNotNone(content_length, "Content-Length header should be set")
        self.assertEqual(int(content_length), len(response.content))

    def test_featureset_with_features_content_length(self):
        """Test that Content-Length is set correctly when features are present"""
        request = self.factory.get(self.api_base + "/featureset/")
        self.force_authenticate(request, self.app_user)
        response = views.FeatureSetGeoJsonView.as_view()(request, id=str(self.category.id))
        self.assertIsNotNone(response)
        self.assertContains(response, "features")
        data = json.loads(response.content)
        self.assertGreater(len(data["features"]), 0)

        # Test that content-length header matches actual content length
        content_length = response.get("Content-Length")
        self.assertIsNotNone(content_length, "Content-Length header should be set")
        self.assertEqual(int(content_length), len(response.content))

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
        groups = SpatialFeatureGroupStatic.objects.by_spatial_type(["MULTILINESTRING"])
        assert groups.count() == 1
        assert spatial_feature_group_linestring_only == groups.first()

    def test_spatialfeaturegroupstatic_filter_out_mixed_or_non_linestring_groups(
        self, spatial_feature_group_mixed_geometry
    ):
        assert SpatialFeatureGroupStatic.objects.exists()
        groups = SpatialFeatureGroupStatic.objects.by_spatial_type(["MULTILINESTRING"])
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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureListJsonView:
    @pytest.fixture
    def empty_multi_polygon(self):
        return SpatialFeatureFactory(feature_geometry=geos.GEOSGeometry("0106000020E610000000000000", srid=4326))

    def test_empty_feature_geometry_ignored(self, empty_multi_polygon, display_category, user_client):
        spatial_feature_type = empty_multi_polygon.feature_type
        spatial_feature_type.display_category = display_category
        spatial_feature_type.save()

        good_polygon = SpatialFeatureFactory(
            feature_type=spatial_feature_type,
            feature_geometry=geos.GEOSGeometry(
                "MULTIPOLYGON(((-122 47, -122 48, -123 48, -123 47, -122 47)))", srid=4326
            ),
        )

        url = reverse("mapping:mapping-featureset-geojson", kwargs={"id": str(display_category.id)})
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data["features"]) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureListView:

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
        assert "features" in data["data"]
        assert data["data"]["type"] == "FeatureCollection"
        features = data["data"]["features"]
        assert len(features) == 3

        # Check structure of all features
        expected_properties = [
            "name",
            "short_name",
            "description",
            "feature_class_id",
            "feature_class_name",
            "feature_set_id",
            "feature_set_name",
        ]

        for feature in features:
            assert "id" in feature
            assert "type" in feature
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
            for prop in expected_properties:
                assert prop in feature["properties"]

    def test_filter_by_feature_class(self, user_client, feature1, feature2, feature3, feature_type1):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_class": str(feature_type1.id)})
        assert response.status_code == 200
        data = response.json()
        features = data["data"]["features"]

        # Only feature1 and feature2 belong to feature_type1
        assert len(features) == 2
        names = [f["properties"]["name"] for f in features]
        assert "Feature One" in names
        assert "Feature Two" in names

    def test_filter_by_multiple_feature_classes(
        self, user_client, feature1, feature2, feature3, feature_type1, feature_type2
    ):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_class": str(feature_type1.id) + "," + str(feature_type2.id)})
        assert response.status_code == 200
        data = response.json()
        features = data["data"]["features"]

        # All features belong to feature_type1 or feature_type2
        assert len(features) == 3
        names = [f["properties"]["name"] for f in features]
        assert "Feature One" in names
        assert "Feature Two" in names
        assert "Feature Three" in names

    def test_filter_by_invalid_feature_class(self, user_client, feature3):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_class": "invalid_uuid"})
        assert response.status_code == 400
        assert "is not a valid UUID" in response.content.decode("utf-8")
        assert "feature_class" in response.json()

        # Feature 3 is not a feature type
        response = user_client.get(url, {"feature_class": str(feature3.id)})
        assert response.status_code == 400
        assert "Select a valid choice." in response.content.decode("utf-8")
        assert "feature_class" in response.json()

    def test_filter_by_feature_set(self, user_client, feature1, feature2, feature3, category2):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_set": str(category2.id)})
        assert response.status_code == 200
        data = response.json()
        features = data["data"]["features"]

        # Only feature3 belongs to category2
        assert len(features) == 1
        assert features[0]["properties"]["name"] == "Feature Three"

    def test_filter_by_multiple_feature_sets(self, user_client, feature1, feature2, feature3, category1, category2):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_set": f"{category1.id},{category2.id}"})
        assert response.status_code == 200
        data = response.json()
        features = data["data"]["features"]

        # All features belong to category1 or category2
        assert len(features) == 3
        names = [f["properties"]["name"] for f in features]
        assert set(names) == {"Feature One", "Feature Two", "Feature Three"}

    def test_filter_by_invalid_feature_set(self, user_client, feature3):
        url = reverse("mapping:spatialfeature-list")
        response = user_client.get(url, {"feature_set": "invalid_uuid"})
        assert response.status_code == 400
        assert "is not a valid UUID" in response.content.decode("utf-8")
        assert "feature_set" in response.json()

        # Feature 3 is not a feature set
        response = user_client.get(url, {"feature_set": str(feature3.id)})
        assert response.status_code == 400
        assert "Select a valid choice." in response.content.decode("utf-8")
        assert "feature_set" in response.json()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureTypeListView:

    def test_list_all_feature_types(self, user_client, feature_type1, feature_type2):
        url = reverse("mapping:spatialfeaturetype-list")
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "status" in data
        assert data["status"]["code"] == 200

        feature_types = data["data"]
        assert len(feature_types) == 2

        # Check structure of all feature types
        expected_fields = ["id", "name", "feature_set_id"]
        for feature_type in feature_types:
            for field in expected_fields:
                assert field in feature_type

        # Verify the specific feature types are present
        names = [ft["name"] for ft in feature_types]
        assert set(names) == {"Type One", "Type Two"}

    def test_feature_types_have_correct_categories(
        self, user_client, feature_type1, feature_type2, category1, category2
    ):
        url = reverse("mapping:spatialfeaturetype-list")
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()
        feature_types = data["data"]

        # Find each feature type in the response
        type_one = next(ft for ft in feature_types if ft["name"] == "Type One")
        type_two = next(ft for ft in feature_types if ft["name"] == "Type Two")

        # Verify they have the correct display categories
        assert str(type_one["feature_set_id"]) == str(category1.id)
        assert str(type_two["feature_set_id"]) == str(category2.id)
