from __future__ import annotations

import json

import pytest

from django.contrib.gis.geos import MultiPoint, Point
from django.urls import reverse

from factories import (
    DisplayCategoryFactory,
    SpatialFeatureFactory,
    SpatialFeatureGroupStaticFactory,
    SpatialFeatureTypeFactory,
)
from mapping.models import (
    DisplayCategory,
    Map,
    SpatialFeature,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDisplayCategoryAPI:

    def test_list_display_categories(self, user_client):
        DisplayCategoryFactory(name="Boundaries")
        DisplayCategoryFactory(name="Water")
        url = reverse("mapping:displaycategories-list")
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2

    def test_create_display_category(self, superuser_client):
        url = reverse("mapping:displaycategories-list")
        payload = {"name": "Security", "description": "Security features"}
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        assert DisplayCategory.objects.filter(name="Security").exists()

    def test_retrieve_display_category(self, user_client):
        cat = DisplayCategoryFactory(name="Boundaries")
        url = reverse("mapping:displaycategories-detail", kwargs={"id": str(cat.id)})
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "Boundaries"

    def test_update_display_category(self, superuser_client):
        cat = DisplayCategoryFactory(name="Boundaries")
        url = reverse("mapping:displaycategories-detail", kwargs={"id": str(cat.id)})
        payload = {"name": "Boundaries Updated", "description": "Updated desc"}
        response = superuser_client.patch(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 200
        cat.refresh_from_db()
        assert cat.name == "Boundaries Updated"

    def test_delete_display_category(self, superuser_client):
        cat = DisplayCategoryFactory(name="Boundaries")
        url = reverse("mapping:displaycategories-detail", kwargs={"id": str(cat.id)})
        response = superuser_client.delete(url)
        assert response.status_code == 200
        assert not DisplayCategory.objects.filter(id=cat.id).exists()

    def test_create_display_category_requires_name(self, superuser_client):
        url = reverse("mapping:displaycategories-list")
        response = superuser_client.post(
            url, data=json.dumps({"description": "No name"}), content_type="application/json"
        )
        assert response.status_code == 400

    def test_write_requires_permission(self, user_client):
        url = reverse("mapping:displaycategories-list")
        response = user_client.post(url, data=json.dumps({"name": "Unauthorized"}), content_type="application/json")
        assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureTypeAPI:

    def test_list_feature_types(self, user_client, display_category):
        SpatialFeatureTypeFactory(name="Type A", display_category=display_category)
        SpatialFeatureTypeFactory(name="Type B", display_category=display_category)
        url = reverse("mapping:featuretypes-list")
        response = user_client.get(url)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 2

    def test_create_feature_type(self, superuser_client, display_category):
        url = reverse("mapping:featuretypes-list")
        payload = {
            "name": "Road",
            "display_category": str(display_category.id),
            "presentation": {},
            "is_visible": True,
        }
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        assert SpatialFeatureType.objects.filter(name="Road").exists()

    def test_retrieve_feature_type(self, user_client, display_category):
        ft = SpatialFeatureTypeFactory(name="River", display_category=display_category)
        url = reverse("mapping:featuretypes-detail", kwargs={"id": str(ft.id)})
        response = user_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "River"

    def test_update_feature_type(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(name="Road", display_category=display_category)
        url = reverse("mapping:featuretypes-detail", kwargs={"id": str(ft.id)})
        payload = {"name": "Highway", "display_category": str(display_category.id)}
        response = superuser_client.patch(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 200
        ft.refresh_from_db()
        assert ft.name == "Highway"

    def test_delete_feature_type(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(name="Road", display_category=display_category)
        url = reverse("mapping:featuretypes-detail", kwargs={"id": str(ft.id)})
        response = superuser_client.delete(url)
        assert response.status_code == 200
        assert not SpatialFeatureType.objects.filter(id=ft.id).exists()

    def test_write_requires_permission(self, user_client, display_category):
        url = reverse("mapping:featuretypes-list")
        payload = {"name": "Road", "display_category": str(display_category.id), "is_visible": True}
        response = user_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestMapAPI:

    @pytest.fixture
    def map_payload(self):
        return {
            "name": "Test Map",
            "center": {"type": "Point", "coordinates": [-122.3, 47.5]},
            "zoom": 12,
            "attributes": {},
        }

    def test_create_map(self, superuser_client, map_payload):
        url = reverse("mapping:quicklinks-list")
        response = superuser_client.post(url, data=json.dumps(map_payload), content_type="application/json")
        assert response.status_code == 201
        assert Map.objects.filter(name="Test Map").exists()

    def test_retrieve_map(self, superuser_client, map_payload):
        url = reverse("mapping:quicklinks-list")
        superuser_client.post(url, data=json.dumps(map_payload), content_type="application/json")
        m = Map.objects.get(name="Test Map")
        detail_url = reverse("mapping:quicklinks-detail", kwargs={"id": str(m.id)})
        response = superuser_client.get(detail_url)
        assert response.status_code == 200

    def test_update_map(self, superuser_client, map_payload):
        url = reverse("mapping:quicklinks-list")
        superuser_client.post(url, data=json.dumps(map_payload), content_type="application/json")
        m = Map.objects.get(name="Test Map")
        detail_url = reverse("mapping:quicklinks-detail", kwargs={"id": str(m.id)})
        update_payload = {**map_payload, "name": "Updated Map", "zoom": 14}
        response = superuser_client.put(detail_url, data=json.dumps(update_payload), content_type="application/json")
        assert response.status_code == 200
        m.refresh_from_db()
        assert m.name == "Updated Map"

    def test_delete_map(self, superuser_client, map_payload):
        url = reverse("mapping:quicklinks-list")
        superuser_client.post(url, data=json.dumps(map_payload), content_type="application/json")
        m = Map.objects.get(name="Test Map")
        detail_url = reverse("mapping:quicklinks-detail", kwargs={"id": str(m.id)})
        response = superuser_client.delete(detail_url)
        assert response.status_code == 200
        assert not Map.objects.filter(id=m.id).exists()

    def test_write_requires_permission(self, user_client, map_payload):
        url = reverse("mapping:quicklinks-list")
        response = user_client.post(url, data=json.dumps(map_payload), content_type="application/json")
        assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeprecatedMapsAPI:

    def test_maps_returns_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/maps/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_quicklinks_has_no_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/quicklink/")
        assert response.status_code == 200
        assert "Deprecation" not in response


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeprecatedFeatureSetAPI:

    def test_featureset_list_returns_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/featureset/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_featureset_detail_returns_deprecation_header(self, user_client, display_category):
        response = user_client.get(f"/api/v1.0/featureset/{display_category.id}/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_featuregroup_list_has_no_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/featuregroup/")
        assert response.status_code == 200
        assert "Deprecation" not in response

    def test_featuregroup_detail_has_no_deprecation_header(self, user_client):
        group = SpatialFeatureGroupStaticFactory(name="Test Group")
        response = user_client.get(f"/api/v1.0/featuregroup/{group.id}/")
        assert response.status_code == 200
        assert "Deprecation" not in response

    def test_featuregroup_list_url_points_to_featuregroup(self, user_client):
        group = SpatialFeatureGroupStaticFactory(name="Test Group")
        response = user_client.get("/api/v1.0/featuregroup/")
        data = response.json()
        item = next(f for f in data["data"] if str(group.id) in f["url"])
        assert "/featuregroup/" in item["url"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeprecatedFeatureClassAPI:

    def test_featureclass_list_returns_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/featureclass/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_featureclass_detail_returns_deprecation_header(self, user_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        response = user_client.get(f"/api/v1.0/featureclass/{ft.id}/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_featuretype_list_has_no_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/featuretype/")
        assert response.status_code == 200
        assert "Deprecation" not in response

    def test_featuretype_detail_has_no_deprecation_header(self, user_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        response = user_client.get(f"/api/v1.0/featuretype/{ft.id}/")
        assert response.status_code == 200
        assert "Deprecation" not in response


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureGroupAPI:

    def test_list_feature_groups(self, user_client):
        SpatialFeatureGroupStaticFactory(name="Group A")
        SpatialFeatureGroupStaticFactory(name="Group B")
        url = reverse("mapping:featuregroups-list")
        response = user_client.get(url)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 2

    def test_retrieve_feature_group(self, user_client):
        group = SpatialFeatureGroupStaticFactory(name="My Group")
        url = reverse("mapping:featuregroups-detail", kwargs={"id": str(group.id)})
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "My Group"

    def test_create_feature_group(self, superuser_client):
        url = reverse("mapping:featuregroups-list")
        payload = {"name": "River Basin Group", "description": "Group of rivers"}
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        assert SpatialFeatureGroupStatic.objects.filter(name="River Basin Group").exists()

    def test_create_feature_group_with_features(self, superuser_client):
        feature = SpatialFeatureFactory(feature_geometry=MultiPoint(Point(-122.1, 47.5)))
        url = reverse("mapping:featuregroups-list")
        payload = {"name": "Group With Features", "description": "", "features": [str(feature.id)]}
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        group = SpatialFeatureGroupStatic.objects.get(name="Group With Features")
        assert group.features.count() == 1

    def test_update_feature_group(self, superuser_client):
        group = SpatialFeatureGroupStaticFactory(name="Old Name")
        url = reverse("mapping:featuregroups-detail", kwargs={"id": str(group.id)})
        payload = {"name": "New Name", "description": "Updated"}
        response = superuser_client.patch(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 200
        group.refresh_from_db()
        assert group.name == "New Name"

    def test_delete_feature_group(self, superuser_client):
        group = SpatialFeatureGroupStaticFactory(name="To Delete")
        url = reverse("mapping:featuregroups-detail", kwargs={"id": str(group.id)})
        response = superuser_client.delete(url)
        assert response.status_code == 200
        assert not SpatialFeatureGroupStatic.objects.filter(id=group.id).exists()

    def test_write_requires_permission(self, user_client):
        url = reverse("mapping:featuregroups-list")
        response = user_client.post(url, data=json.dumps({"name": "No Permission"}), content_type="application/json")
        assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureAPI:

    def test_list_features(self, user_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        SpatialFeatureFactory(name="Feature 1", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        SpatialFeatureFactory(name="Feature 2", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        url = reverse("mapping_v2:feature-list")
        response = user_client.get(url)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 2

    def test_retrieve_feature(self, user_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        feature = SpatialFeatureFactory(name="My Feature", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        url = reverse("mapping_v2:feature-detail", kwargs={"id": str(feature.id)})
        response = user_client.get(url)
        assert response.status_code == 200

    def test_create_feature(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(name="Road", display_category=display_category)
        url = reverse("mapping_v2:feature-list")
        payload = {
            "name": "Main Road",
            "feature_type": str(ft.id),
            "feature_geometry": {
                "type": "Point",
                "coordinates": [-122.3, 47.5],
            },
        }
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        assert SpatialFeature.objects.filter(name="Main Road").exists()

    def test_update_feature(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        feature = SpatialFeatureFactory(name="Old Feature", feature_type=ft, feature_geometry=Point(-122.1, 47.5))
        url = reverse("mapping_v2:feature-detail", kwargs={"id": str(feature.id)})
        payload = {
            "name": "Updated Feature",
            "feature_type": str(ft.id),
            "feature_geometry": {"type": "Point", "coordinates": [-122.2, 47.6]},
        }
        response = superuser_client.patch(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 200
        feature.refresh_from_db()
        assert feature.name == "Updated Feature"

    def test_delete_feature(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        feature = SpatialFeatureFactory(feature_type=ft, feature_geometry=Point(-122.1, 47.5))
        url = reverse("mapping_v2:feature-detail", kwargs={"id": str(feature.id)})
        response = superuser_client.delete(url)
        assert response.status_code == 200
        assert not SpatialFeature.objects.filter(id=feature.id).exists()

    def test_create_feature_requires_feature_type(self, superuser_client):
        url = reverse("mapping_v2:feature-list")
        payload = {
            "name": "Nameless Road",
            "feature_geometry": {"type": "Point", "coordinates": [-122.3, 47.5]},
        }
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 400

    def test_create_feature_normalizes_point_to_multipoint(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        url = reverse("mapping_v2:feature-list")
        payload = {
            "name": "Point Feature",
            "feature_type": str(ft.id),
            "feature_geometry": {"type": "Point", "coordinates": [-122.3, 47.5]},
        }
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        feature = SpatialFeature.objects.get(name="Point Feature")
        assert feature.feature_geometry.geom_type == "MultiPoint"

    def test_create_feature_normalizes_linestring_to_multilinestring(self, superuser_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        url = reverse("mapping_v2:feature-list")
        payload = {
            "name": "Line Feature",
            "feature_type": str(ft.id),
            "feature_geometry": {
                "type": "LineString",
                "coordinates": [[-122.3, 47.5], [-122.4, 47.6]],
            },
        }
        response = superuser_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201
        feature = SpatialFeature.objects.get(name="Line Feature")
        assert feature.feature_geometry.geom_type == "MultiLineString"

    def test_write_requires_permission(self, user_client, display_category):
        ft = SpatialFeatureTypeFactory(display_category=display_category)
        url = reverse("mapping_v2:feature-list")
        payload = {
            "name": "Unauthorized Feature",
            "feature_type": str(ft.id),
            "feature_geometry": {"type": "Point", "coordinates": [-122.3, 47.5]},
        }
        response = user_client.post(url, data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeprecatedSpatialFeatureAPI:

    def test_spatialfeature_list_returns_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/spatialfeature/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_spatialfeature_detail_returns_deprecation_header(self, user_client):
        ft = SpatialFeatureTypeFactory()
        feature = SpatialFeatureFactory(feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        response = user_client.get(f"/api/v1.0/spatialfeature/{feature.id}/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"
        assert "Warning" in response

    def test_features_list_has_deprecation_header(self, user_client):
        response = user_client.get("/api/v1.0/features/")
        assert response.status_code == 200
        assert response["Deprecation"] == "true"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFeatureListFilters:

    def test_filter_by_feature_type(self, user_client):
        ft_a = SpatialFeatureTypeFactory()
        ft_b = SpatialFeatureTypeFactory()
        SpatialFeatureFactory(name="Alpha", feature_type=ft_a, feature_geometry=Point(-122.3, 47.5))
        SpatialFeatureFactory(name="Beta", feature_type=ft_b, feature_geometry=Point(-122.3, 47.5))

        response = user_client.get("/api/v1.0/features/", {"feature_type": str(ft_a.id)})
        assert response.status_code == 200
        names = [f["name"] for f in response.json()["features"]]
        assert names == ["Alpha"]

    def test_filter_by_feature_set(self, user_client):
        ft = SpatialFeatureTypeFactory()
        in_group = SpatialFeatureFactory(name="In Group", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        SpatialFeatureFactory(name="Not In Group", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        group = SpatialFeatureGroupStaticFactory()
        group.features.add(in_group)

        response = user_client.get("/api/v1.0/features/", {"feature_set": str(group.id)})
        assert response.status_code == 200
        names = [f["name"] for f in response.json()["features"]]
        assert names == ["In Group"]

    def test_filter_by_feature_type_and_feature_set(self, user_client):
        ft_a = SpatialFeatureTypeFactory()
        ft_b = SpatialFeatureTypeFactory()
        f_a = SpatialFeatureFactory(name="A", feature_type=ft_a, feature_geometry=Point(-122.3, 47.5))
        f_b = SpatialFeatureFactory(name="B", feature_type=ft_b, feature_geometry=Point(-122.3, 47.5))
        group = SpatialFeatureGroupStaticFactory()
        group.features.add(f_a, f_b)

        response = user_client.get("/api/v1.0/features/", {"feature_type": str(ft_a.id), "feature_set": str(group.id)})
        assert response.status_code == 200
        names = [f["name"] for f in response.json()["features"]]
        assert names == ["A"]

    def test_sort_by_name_ascending(self, user_client):
        ft = SpatialFeatureTypeFactory()
        SpatialFeatureFactory(name="Zebra", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        SpatialFeatureFactory(name="Apple", feature_type=ft, feature_geometry=Point(-122.3, 47.5))

        response = user_client.get("/api/v1.0/features/", {"sort_by": "name"})
        assert response.status_code == 200
        names = [f["name"] for f in response.json()["features"]]
        assert names == sorted(names)

    def test_sort_by_name_descending(self, user_client):
        ft = SpatialFeatureTypeFactory()
        SpatialFeatureFactory(name="Zebra", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        SpatialFeatureFactory(name="Apple", feature_type=ft, feature_geometry=Point(-122.3, 47.5))

        response = user_client.get("/api/v1.0/features/", {"sort_by": "-name"})
        assert response.status_code == 200
        names = [f["name"] for f in response.json()["features"]]
        assert names == sorted(names, reverse=True)

    def test_invalid_sort_by_falls_back_to_name(self, user_client):
        ft = SpatialFeatureTypeFactory()
        SpatialFeatureFactory(name="Zebra", feature_type=ft, feature_geometry=Point(-122.3, 47.5))
        SpatialFeatureFactory(name="Apple", feature_type=ft, feature_geometry=Point(-122.3, 47.5))

        response = user_client.get("/api/v1.0/features/", {"sort_by": "nonexistent_field"})
        assert response.status_code == 200
        names = [f["name"] for f in response.json()["features"]]
        assert names == sorted(names)
