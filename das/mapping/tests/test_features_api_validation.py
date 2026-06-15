"""Validate that the /features/ and /feature/<id>/ APIs cover the scenarios
tested by the old TestSpatialFeatureAPI and TestSpatialFeatureListView suites.
"""

from __future__ import annotations

import json

import pytest

from django.contrib.gis.geos import Point

from mapping.models import SpatialFeature


@pytest.fixture
def feature1(feature_type1):
    return SpatialFeature.objects.create(
        name="Feature One", feature_type=feature_type1, feature_geometry=Point(-122.1, 47.5)
    )


@pytest.fixture
def feature2(feature_type1):
    return SpatialFeature.objects.create(
        name="Feature Two", feature_type=feature_type1, feature_geometry=Point(-122.2, 47.6)
    )


@pytest.fixture
def feature3(feature_type2):
    return SpatialFeature.objects.create(
        name="Feature Three", feature_type=feature_type2, feature_geometry=Point(-122.3, 47.7)
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFeaturesAPIValidation:
    """Each test mirrors a scenario from TestSpatialFeatureListView or
    TestSpatialFeatureAPI but targets /features/ and /feature/<id>/."""

    # ------------------------------------------------------------------ list

    def test_list_returns_200(self, user_client, feature1, feature2, feature3):
        response = user_client.get("/api/v1.0/features/")
        assert response.status_code == 200

    def test_list_response_shape(self, user_client, feature1, feature2, feature3):
        response = user_client.get("/api/v1.0/features/")
        data = response.json()
        assert "features" in data
        assert len(data["features"]) == 3
        item = data["features"][0]
        for field in ("name", "type", "description", "geojson_url"):
            assert field in item, f"missing field: {field}"
        assert "name" in item["type"]
        assert "id" in item["type"]

    # ------------------------------------------------------------------ filter by feature_type

    def test_filter_by_feature_type(self, user_client, feature1, feature2, feature3, feature_type1):
        response = user_client.get("/api/v1.0/features/", {"feature_type": str(feature_type1.id)})
        assert response.status_code == 200
        names = {f["name"] for f in response.json()["features"]}
        assert names == {"Feature One", "Feature Two"}

    def test_filter_by_feature_type_excludes_others(self, user_client, feature1, feature2, feature3, feature_type2):
        response = user_client.get("/api/v1.0/features/", {"feature_type": str(feature_type2.id)})
        assert response.status_code == 200
        names = {f["name"] for f in response.json()["features"]}
        assert names == {"Feature Three"}

    # ------------------------------------------------------------------ filter by feature_set (SpatialFeatureGroupStatic)
    # /features/ ``feature_set`` filters by SpatialFeatureGroupStatic — this is the legacy v1
    # semantics, intentionally preserved. The v2 endpoint exposes the
    # DisplayCategory equivalent as ``display_category`` to avoid silent
    # cross-meaning of the same param name across versions.

    def test_filter_by_display_category_not_supported(self, user_client, feature1, feature2, feature3, category2):
        """Passing a DisplayCategory ID has no effect on v1 ``/features/`` —
        ``feature_set`` here means SpatialFeatureGroupStatic."""
        response = user_client.get("/api/v1.0/features/", {"feature_set": str(category2.id)})
        assert response.status_code == 200
        # category2.id is not a SpatialFeatureGroupStatic id, so no features match
        assert response.json()["features"] == []

    # ------------------------------------------------------------------ write operations

    def test_create_not_supported(self, superuser_client, feature_type1):
        payload = {
            "name": "New Feature",
            "feature_type": str(feature_type1.id),
            "feature_geometry": {"type": "Point", "coordinates": [-122.3, 47.5]},
        }
        response = superuser_client.post(
            "/api/v1.0/features/", data=json.dumps(payload), content_type="application/json"
        )
        assert response.status_code == 405

    def test_update_not_supported(self, superuser_client, feature1):
        payload = {"name": "Updated Name"}
        response = superuser_client.patch(
            f"/api/v1.0/feature/{feature1.id}/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 405

    def test_delete_not_supported(self, superuser_client, feature1):
        response = superuser_client.delete(f"/api/v1.0/feature/{feature1.id}/")
        assert response.status_code == 405

    # ------------------------------------------------------------------ sort

    def test_default_sort_is_by_name(self, user_client, feature1, feature2, feature3):
        response = user_client.get("/api/v1.0/features/")
        names = [f["name"] for f in response.json()["features"]]
        assert names == sorted(names)

    def test_sort_by_name_descending(self, user_client, feature1, feature2, feature3):
        response = user_client.get("/api/v1.0/features/", {"sort_by": "-name"})
        names = [f["name"] for f in response.json()["features"]]
        assert names == sorted(names, reverse=True)

    # ------------------------------------------------------------------ query param validation

    def test_malformed_feature_type_returns_400(self, user_client):
        response = user_client.get("/api/v1.0/features/", {"feature_type": "not-a-uuid"})
        assert response.status_code == 400
        assert "feature_type" in response.json()

    def test_malformed_feature_set_returns_400(self, user_client):
        response = user_client.get("/api/v1.0/features/", {"feature_set": "also-not-a-uuid"})
        assert response.status_code == 400
        assert "feature_set" in response.json()
