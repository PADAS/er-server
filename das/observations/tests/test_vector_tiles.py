"""Test suite for ObservationVectorLayer and tile endpoint (no host-based image prefixing)."""

import pytest
from vectortiles.views import MVTView

from django.conf import settings
from django.test import RequestFactory

import utils.tenant.providers as tenant_providers
from observations.models import Observation
from observations.vector_layers import ObservationVectorLayer
from observations.views import ObservationTileView


@pytest.mark.django_db
class TestObservationVectorLayer:
    def test_basic_config(self):
        layer = ObservationVectorLayer()
        assert layer.model is Observation
        assert layer.id == "observations"
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24

        for field in [
            "id",
            "recorded_at",
            # "recorded_at",
            # "subject_id",
            # "subject_name",
            # "source_id",
            # "source_name",
            # "track_segment_id",
            # "segment_order",
            # "speed_kmh",
            "additional",
        ]:
            assert field in layer.tile_fields

    def test_default_thresholds_and_accessors_without_request(self):
        layer = ObservationVectorLayer()
        assert layer.DEFAULT_MAX_TIME_GAP_HOURS == 24
        assert layer.DEFAULT_SPEED_THRESHOLD_KMH == 200.0
        assert layer._get_max_time_gap_hours() == float(layer.DEFAULT_MAX_TIME_GAP_HOURS)
        assert layer._get_speed_threshold_kmh() == float(layer.DEFAULT_SPEED_THRESHOLD_KMH)

    def test_presentation_keys_exposed(self):
        layer = ObservationVectorLayer()
        for key in ["stroke", "stroke-width", "stroke-opacity"]:
            assert key in getattr(layer, "presentation_keys", [])


@pytest.mark.django_db
class TestObservationTileEndpoint:
    def _mk_request(
        self,
        path="/api/v1.0/observations/tiles/10/512/512.pbf",
        host="example.org",
        auth="Bearer faketoken",
    ):
        factory = RequestFactory()
        return factory.get(path, HTTP_HOST=host, HTTP_AUTHORIZATION=auth)

    def _patch_tenant_everywhere(self, monkeypatch, host="example.org"):
        """
        Patch tenant resolution at ALL likely call sites:
        - The global utils.tenant.providers module
        - The ObservationTileView's module namespace (where helpers may be imported)
        - Any local `providers` alias inside that module
        """
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", [host])

        # Minimal stubs
        def _domain_for_alt_server_name(h):
            return h

        def _data_for_host(h):
            return {"domain": h}

        # 1) Patch the global providers module
        monkeypatch.setattr(
            tenant_providers, "get_tenant_domain_for_alt_server_name", _domain_for_alt_server_name, raising=False
        )
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_alt_server_name", _data_for_host, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_host", _data_for_host, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_domain", _data_for_host, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_request_host", _data_for_host, raising=False)

        # 2) Patch the *view module* where helpers might be imported into local names
        view_mod_name = ObservationTileView.__module__
        view_mod = __import__(view_mod_name, fromlist=["*"])

        monkeypatch.setattr(
            view_mod, "get_tenant_domain_for_alt_server_name", _domain_for_alt_server_name, raising=False
        )
        monkeypatch.setattr(view_mod, "get_tenant_data_by_alt_server_name", _data_for_host, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_host", _data_for_host, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_domain", _data_for_host, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_request_host", _data_for_host, raising=False)

        # 3) If the view module imported the providers module as an alias (e.g., `import utils.tenant.providers as providers`)
        if hasattr(view_mod, "providers"):
            prov = view_mod.providers
            monkeypatch.setattr(
                prov, "get_tenant_domain_for_alt_server_name", _domain_for_alt_server_name, raising=False
            )
            monkeypatch.setattr(prov, "get_tenant_data_by_alt_server_name", _data_for_host, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_host", _data_for_host, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_domain", _data_for_host, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_request_host", _data_for_host, raising=False)

    def test_tile_view_instantiation_and_layer_injection(self, monkeypatch):
        self._patch_tenant_everywhere(monkeypatch)

        class DummyUser:
            id = "user-obs-1"
            das_tenant_id = "tenantXYZ"
            is_authenticated = True

            def has_perms(self, perms):
                return True

            def has_any_perms(self, perms):
                return True

        req = self._mk_request()
        req.user = DummyUser()

        view = ObservationTileView()
        resp = view.get(req, 10, 512, 512)
        assert resp.status_code in (200, 204)
        assert hasattr(view, "layers")
        assert isinstance(view.layers[0], ObservationVectorLayer)
        view.setup(req)
        assert len(view.layer_classes) == 1
        assert view.layer_classes[0] == ObservationVectorLayer

    def test_tile_view_missing_user_or_auth_returns_401(self, monkeypatch):
        self._patch_tenant_everywhere(monkeypatch)
        factory = RequestFactory()

        # No Authorization header and no user attached
        req1 = factory.get("/api/v1.0/observations/tiles/5/10/12.pbf", HTTP_HOST="example.org")
        view = ObservationTileView()
        r1 = view.get(req1, 5, 10, 12)
        assert r1.status_code == 401
        assert r1["WWW-Authenticate"].startswith("Bearer")

        class UserNoTenant:
            id = "u-obs-1"
            das_tenant_id = None

        req2 = factory.get(
            "/api/v1.0/observations/tiles/5/10/12.pbf",
            HTTP_HOST="example.org",
            HTTP_AUTHORIZATION="Bearer t",
        )
        req2.user = UserNoTenant()
        r2 = view.get(req2, 5, 10, 12)
        assert r2.status_code == 401

    def test_tile_view_cache_hit_serves_cached_payload(self, monkeypatch):
        self._patch_tenant_everywhere(monkeypatch)
        factory = RequestFactory()
        req = factory.get(
            "/api/v1.0/observations/tiles/8/128/256.pbf",
            HTTP_HOST="example.org",
            HTTP_AUTHORIZATION="Bearer z",
        )

        class U:
            id = "user-obs-99"
            das_tenant_id = "tenantXYZ"
            is_authenticated = True

            def has_perms(self, perms):
                return True

            def has_any_perms(self, perms):
                return True

        req.user = U()

        call_record = {"count": 0}

        def fake_get(self, request, z, x, y):  # pragma: no cover
            call_record["count"] += 1
            from django.http import HttpResponse

            return HttpResponse(b"obs-tile", content_type="application/x-protobuf")

        monkeypatch.setattr(MVTView, "get", fake_get)

        view = ObservationTileView()
        r1 = view.get(req, 8, 128, 256)
        assert call_record["count"] == 1
        assert r1["Cache-Control"].startswith("public")

        # Second identical request => cache hit
        r2 = view.get(req, 8, 128, 256)
        assert call_record["count"] == 1
        assert r2.content == b"obs-tile"
        assert r2["Cache-Control"] == r1["Cache-Control"]

    def test_tile_view_tenant_resolution_failure_returns_500(self, monkeypatch):
        # Ensure we *don't* patch success-path here
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["bad.example"])

        def raise_resolve(host):
            raise Exception("tenant resolution failed")

        # Patch global providers with raising behavior
        monkeypatch.setattr(tenant_providers, "get_tenant_domain_for_alt_server_name", raise_resolve, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_alt_server_name", raise_resolve, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_host", raise_resolve, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_domain", raise_resolve, raising=False)
        monkeypatch.setattr(tenant_providers, "get_tenant_data_by_request_host", raise_resolve, raising=False)

        # Also patch the view module/alias to raise in case it imports locally
        view_mod_name = ObservationTileView.__module__
        view_mod = __import__(view_mod_name, fromlist=["*"])
        monkeypatch.setattr(view_mod, "get_tenant_domain_for_alt_server_name", raise_resolve, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_alt_server_name", raise_resolve, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_host", raise_resolve, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_domain", raise_resolve, raising=False)
        monkeypatch.setattr(view_mod, "get_tenant_data_by_request_host", raise_resolve, raising=False)
        if hasattr(view_mod, "providers"):
            prov = view_mod.providers
            monkeypatch.setattr(prov, "get_tenant_domain_for_alt_server_name", raise_resolve, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_alt_server_name", raise_resolve, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_host", raise_resolve, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_domain", raise_resolve, raising=False)
            monkeypatch.setattr(prov, "get_tenant_data_by_request_host", raise_resolve, raising=False)

        factory = RequestFactory()
        req = factory.get(
            "/api/v1.0/observations/tiles/3/4/5.pbf",
            HTTP_HOST="bad.example",
            HTTP_AUTHORIZATION="Bearer a",
        )

        class U:
            id = "u1"
            das_tenant_id = "t1"
            is_authenticated = True

            def has_perms(self, perms):
                return True

            def has_any_perms(self, perms):
                return True

        req.user = U()
        view = ObservationTileView()
        resp = view.get(req, 3, 4, 5)
        assert resp.status_code == 500
