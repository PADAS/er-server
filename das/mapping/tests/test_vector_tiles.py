"""Test suite for SpatialFeatureLayer and tile endpoint (no host-based image prefixing)."""

import pytest
from vectortiles.views import MVTView

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db.models import Case
from django.test import RequestFactory

import mapping.views as mviews
from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType
from mapping.vector_layers import SpatialFeatureLayer
from mapping.views import SpatialFeatureTileView


@pytest.mark.django_db
class TestSpatialFeatureLayer:
    def test_basic_config(self):
        layer = SpatialFeatureLayer()
        assert layer.model.__name__ == "SpatialFeature"
        assert layer.id == "spatial_features"
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24
        # Check essential fields are present
        assert "id" in layer.tile_fields
        assert "name" in layer.tile_fields
        assert "image" in layer.tile_fields

    def test_image_normalization_relative_absolute_and_data(self):
        dc = DisplayCategory.objects.create(name="Img")
        ft = SpatialFeatureType.objects.create(name="Type", display_category=dc, presentation={})
        f1 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Slash",
            presentation={"image": "/static/a.svg"},
            feature_geometry=Point(0, 0),
        )
        f2 = SpatialFeature.objects.create(
            feature_type=ft,
            name="NoSlash",
            presentation={"image": "static/b.svg"},
            feature_geometry=Point(1, 1),
        )
        abs_url = "https://cdn.example.com/img/c.svg"
        f3 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Abs",
            presentation={"image": abs_url},
            feature_geometry=Point(2, 2),
        )
        data_uri = "data:image/png;base64,AAA="
        f4 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Data",
            presentation={"image": data_uri},
            feature_geometry=Point(3, 3),
        )
        layer = SpatialFeatureLayer()
        qs = layer.get_vector_tile_queryset(10, 0, 0).filter(id__in=[f1.id, f2.id, f3.id, f4.id])
        got = {r.id: r.image for r in qs}
        assert got[f1.id] == "/static/a.svg"
        assert got[f2.id] == "static/b.svg"
        assert got[f3.id] == abs_url
        assert got[f4.id] == data_uri

    def test_image_normalization_nested_and_null(self):
        dc = DisplayCategory.objects.create(name="Nested")
        ft = SpatialFeatureType.objects.create(name="TypeN", display_category=dc, presentation={})
        fn = SpatialFeature.objects.create(
            feature_type=ft,
            name="Nested",
            presentation={"image": {"image": "nested_icon.svg", "width": 12}},
            feature_geometry=Point(4, 4),
        )
        fnull = SpatialFeature.objects.create(
            feature_type=ft, name="Null", presentation={}, feature_geometry=Point(5, 5)
        )
        layer = SpatialFeatureLayer()
        qs = layer.get_vector_tile_queryset(10, 0, 0).filter(id__in=[fn.id, fnull.id])
        got = {r.id: r.image for r in qs}
        assert got[fn.id] == "nested_icon.svg"
        assert got[fnull.id] is None

    def test_layer_initialization_without_base_root(self):
        SpatialFeatureLayer()  # should not raise

    def test_extract_presentation_keys(self):
        dc = DisplayCategory.objects.create(name="Style")
        ft = SpatialFeatureType.objects.create(
            name="TypeS",
            display_category=dc,
            presentation={
                "stroke": "#ff0000",
                "stroke-width": 2,
                "fill-color": "#00ff00",
                "fill-opacity": 0.5,
                "custom-field": "x",
            },
        )
        SpatialFeature.objects.create(feature_type=ft, name="Feature", feature_geometry=Point(6, 6))
        layer = SpatialFeatureLayer()
        annotations = layer._extract_presentation_json_keys()
        for key in ["stroke", "stroke-width", "fill-color", "fill-opacity"]:
            if key in layer.tile_fields:
                assert key in annotations
                assert isinstance(annotations[key], Case)
        assert "custom-field" not in annotations

    def test_queryset_includes_presentation_keys(self):
        dc = DisplayCategory.objects.create(name="Q")
        ft = SpatialFeatureType.objects.create(
            name="TypeQ",
            display_category=dc,
            presentation={
                "stroke": "#ff0000",
                "stroke-width": 2,
                "fill-color": "#00ff00",
                "fill-opacity": 0.5,
            },
        )
        feat = SpatialFeature.objects.create(feature_type=ft, name="FeatQ", feature_geometry=Point(7, 7))
        layer = SpatialFeatureLayer()
        obj = layer.get_vector_tile_queryset(10, 0, 0).filter(id=feat.id).first()
        assert obj.stroke == "#ff0000"
        width_val = getattr(obj, "stroke-width", None) or getattr(obj, "stroke_width", None)
        assert width_val == 2

        def test_queryset_geometry_is_reprojected_to_3857(self):
            dc = DisplayCategory.objects.create(name="SRIDTest")
            ft = SpatialFeatureType.objects.create(name="TypeSRID", display_category=dc, presentation={})
            point = Point(10, 20, srid=4326)
            feat = SpatialFeature.objects.create(
                feature_type=ft,
                name="SRIDFeature",
                feature_geometry=point,
            )
            layer = SpatialFeatureLayer()
            obj = layer.get_queryset().filter(id=feat.id).first()
            geom = getattr(obj, "geom", None)
            assert geom is not None
            assert geom.srid == 3857

    def test_webmercator_geometry_used_when_populated(self):
        """Test that pre-computed webmercator geometry is used when available"""
        dc = DisplayCategory.objects.create(name="Optimized")
        ft = SpatialFeatureType.objects.create(name="OptimizedType", display_category=dc)

        # Create feature and let save() populate webmercator field
        feature = SpatialFeature.objects.create(feature_type=ft, name="TestOptimized", feature_geometry=Point(2, 2))

        # Verify webmercator field was populated
        feature.refresh_from_db()
        assert feature.feature_geometry_webmercator is not None

        layer = SpatialFeatureLayer()
        # This should use the pre-computed geometry
        qs = layer.get_vector_tile_queryset(10, 0, 0).filter(id=feature.id)
        obj = list(qs)[0]

        # Should have geometry from pre-computed field
        geom = getattr(obj, "geom", None)
        assert geom is not None
        assert geom.srid == 3857

    def test_generate_webmercator_geometry_basic_correctness(self):
        """Test that geometry generation produces correctly transformed and simplified geometries"""
        dc = DisplayCategory.objects.create(name="Generation")
        ft = SpatialFeatureType.objects.create(name="GenerationType", display_category=dc)

        # Test with a simple point
        feature = SpatialFeature.objects.create(
            feature_type=ft, name="TestPoint", feature_geometry=Point(0, 0)  # WGS84 origin
        )

        # Check that webmercator geometry was generated
        feature.refresh_from_db()
        webmerc_geom = feature.feature_geometry_webmercator
        assert webmerc_geom is not None
        assert webmerc_geom.srid == 3857

        # Basic sanity check - should be near Web Mercator origin
        # (0,0 in WGS84 transforms to roughly (0,0) in Web Mercator)
        assert abs(webmerc_geom.x) < 1000  # Within 1km of origin
        assert abs(webmerc_geom.y) < 1000

    def test_spatialfeature_save_populates_webmercator(self):
        """Test that saving a SpatialFeature auto-generates webmercator geometry"""
        dc = DisplayCategory.objects.create(name="AutoGen")
        ft = SpatialFeatureType.objects.create(name="AutoGenType", display_category=dc)

        # Create without webmercator field
        feature = SpatialFeature(feature_type=ft, name="TestAutoGen", feature_geometry=Point(3, 3))
        assert feature.feature_geometry_webmercator is None

        # Save should auto-generate webmercator field
        feature.save()
        assert feature.feature_geometry_webmercator is not None
        assert feature.feature_geometry_webmercator.srid == 3857

        # Update geometry and save again
        feature.feature_geometry = Point(4, 4)
        feature.save()

        # Should regenerate webmercator field
        feature.refresh_from_db()
        assert feature.feature_geometry_webmercator is not None
        assert feature.feature_geometry_webmercator.srid == 3857


@pytest.mark.django_db
class TestSpatialFeatureTileEndpoint:
    def test_tile_view_instantiation_and_layer_injection(self, monkeypatch):
        # Permit example.org host for this test
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["example.org"])
        # Patch the symbol actually used in the view module
        monkeypatch.setattr(mviews, "get_tenant_data_by_host", lambda host: {"domain": host})
        factory = RequestFactory()
        request = factory.get(
            "/api/v1.0/mapping/tiles/10/512/512.pbf",
            HTTP_HOST="example.org",
            HTTP_AUTHORIZATION="Bearer faketoken",
        )

        class DummyUser:
            id = "user-1"
            das_tenant_id = "tenant123"

        request.user = DummyUser()
        view = SpatialFeatureTileView()
        response = view.get(request, 10, 512, 512)
        assert response.status_code in (200, 204)
        assert hasattr(view, "layers")
        assert isinstance(view.layers[0], SpatialFeatureLayer)
        view.setup(request)
        assert len(view.layer_classes) == 1
        assert view.layer_classes[0] == SpatialFeatureLayer

    def test_tile_view_missing_user_or_auth_returns_401(self, monkeypatch):
        """Requests without authenticated user (missing id/tenant) should 401."""
        from django.conf import settings

        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["example.org"])
        # Tenant resolution OK
        monkeypatch.setattr(mviews, "get_tenant_data_by_host", lambda host: {"domain": host})
        factory = RequestFactory()
        # No Authorization header and no user attached
        request = factory.get("/api/v1.0/mapping/tiles/5/10/12.pbf", HTTP_HOST="example.org")
        view = SpatialFeatureTileView()
        resp = view.get(request, 5, 10, 12)
        assert resp.status_code == 401
        assert resp["WWW-Authenticate"].startswith("Bearer")

        # Attach user lacking das_tenant_id to trigger ValueError in cache key
        class UserNoTenant:
            id = "u-1"
            das_tenant_id = None

        request2 = factory.get(
            "/api/v1.0/mapping/tiles/5/10/12.pbf", HTTP_HOST="example.org", HTTP_AUTHORIZATION="Bearer t"
        )
        request2.user = UserNoTenant()
        resp2 = view.get(request2, 5, 10, 12)
        assert resp2.status_code == 401

    def test_tile_view_cache_hit_serves_cached_payload(self, monkeypatch):
        """Second identical request should not call underlying MVTView.get again and should preserve Cache-Control."""
        from django.conf import settings

        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["example.org"])
        monkeypatch.setattr(mviews, "get_tenant_data_by_host", lambda host: {"domain": host})
        factory = RequestFactory()
        request = factory.get(
            "/api/v1.0/mapping/tiles/8/128/256.pbf", HTTP_HOST="example.org", HTTP_AUTHORIZATION="Bearer z"
        )

        class U:
            id = "user-99"
            das_tenant_id = "tenant123"

        request.user = U()

        # Patch base MVTView.get to observe call count and return deterministic content
        call_record = {"count": 0}

        def fake_get(self, request, z, x, y):  # pragma: no cover - we assert via count
            call_record["count"] += 1
            return HttpResponse(b"tile-bytes", content_type="application/vnd.mapbox-vector-tile")

        from django.http import HttpResponse

        monkeypatch.setattr(MVTView, "get", fake_get)

        view = SpatialFeatureTileView()
        r1 = view.get(request, 8, 128, 256)
        assert call_record["count"] == 1
        assert r1["Cache-Control"].startswith("public")
        # Second identical request
        r2 = view.get(request, 8, 128, 256)
        assert call_record["count"] == 1  # unchanged => cache hit
        assert r2.content == b"tile-bytes"
        assert r2["Cache-Control"] == r1["Cache-Control"]

    def test_tile_view_tenant_resolution_failure_returns_500(self, monkeypatch):
        """Failure to resolve tenant host should result in 500 (security hard-fail)."""
        from django.conf import settings

        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["bad.example"])
        # Force tenant resolution to raise

        def raise_resolve(host):
            raise Exception("tenant resolution failed")

        monkeypatch.setattr(mviews, "get_tenant_data_by_host", raise_resolve)
        factory = RequestFactory()
        req = factory.get("/api/v1.0/mapping/tiles/3/4/5.pbf", HTTP_HOST="bad.example", HTTP_AUTHORIZATION="Bearer a")

        class U:
            id = "u1"
            das_tenant_id = "t1"

        req.user = U()
        view = SpatialFeatureTileView()
        resp = view.get(req, 3, 4, 5)
        assert resp.status_code == 500
