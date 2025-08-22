from unittest.mock import patch

import pytest

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from mapping.cache import build_tile_cache_key
from mapping.views import SpatialFeatureTileView


class DummyUser:
    def __init__(self, tenant_id=None):
        self.das_tenant_id = tenant_id


@pytest.mark.django_db
def test_build_tile_cache_key_requires_bearer_token():
    rf = RequestFactory()
    req = rf.get("/api/v1.0/mapping/tiles/10/1/1.pbf")
    req.user = DummyUser("tenant123")
    with pytest.raises(ValueError):
        build_tile_cache_key(req, 10, 1, 1, ["spatial_features"])  # missing auth header


@pytest.mark.django_db
def test_build_tile_cache_key_basic():
    rf = RequestFactory()
    req = rf.get("/api/v1.0/mapping/tiles/5/16/23.pbf?b=2&a=1&a=2")
    req.META["HTTP_AUTHORIZATION"] = "Bearer tok_ABC123"
    req.user = DummyUser("tenantXYZ")
    key = build_tile_cache_key(req, 5, 16, 23, ["spatial_features"], cache_version="7")
    # Key: vt:{tenant}:{token_hash}:{layers}:{version}:{z}:{x}:{y}:{query_hash}
    parts = key.split(":")
    assert parts[0] == "vt"
    assert parts[1] == "tenantXYZ"
    assert len(parts[2]) == 16  # token hash
    assert parts[3] == "spatial_features"
    assert parts[4] == "7"
    assert parts[5] == "5"
    assert parts[6] == "16"
    assert parts[7] == "23"
    assert len(parts[8]) == 10  # query hash
    assert "tok_ABC123" not in key


@pytest.mark.django_db
def test_build_tile_cache_key_query_order_invariance():
    rf = RequestFactory()
    r1 = rf.get("/api/v1.0/mapping/tiles/5/16/23.pbf?a=1&b=2&c=3")
    r2 = rf.get("/api/v1.0/mapping/tiles/5/16/23.pbf?c=3&b=2&a=1")
    for r in (r1, r2):
        r.META["HTTP_AUTHORIZATION"] = "Bearer tokenX"
        r.user = DummyUser("tenantA")
    k1 = build_tile_cache_key(r1, 5, 16, 23, ["spatial_features"], cache_version="1")
    k2 = build_tile_cache_key(r2, 5, 16, 23, ["spatial_features"], cache_version="1")
    assert k1 == k2


@pytest.mark.django_db
def test_build_tile_cache_key_multiple_layers_sorted():
    rf = RequestFactory()
    req_unsorted = rf.get("/api/v1.0/mapping/tiles/4/10/11.pbf")
    req_unsorted.META["HTTP_AUTHORIZATION"] = "Bearer tokenY"
    req_unsorted.user = DummyUser("tenantB")
    key_unsorted = build_tile_cache_key(req_unsorted, 4, 10, 11, ["layerZ", "layerA"], cache_version="3")
    # Expect layers ordered lexicographically in the key
    # Key: vt:{tenant}:{token_hash}:{layers}:{version}:{z}:{x}:{y}:{query_hash}
    parts = key_unsorted.split(":")
    assert parts[3] == "layerA,layerZ"
    assert parts[4] == "3"
    assert parts[5] == "4"
    assert parts[6] == "10"
    assert parts[7] == "11"


@pytest.mark.django_db
def test_build_tile_cache_key_include_query_false():
    rf = RequestFactory()
    req = rf.get("/api/v1.0/mapping/tiles/6/20/21.pbf?a=1&b=2")
    req.META["HTTP_AUTHORIZATION"] = "Bearer tokQQ"
    req.user = DummyUser("tenantC")
    key = build_tile_cache_key(req, 6, 20, 21, ["spatial_features"], cache_version="5", include_query=False)
    assert key.endswith(":noquery")
    parts = key.split(":")
    assert parts[0] == "vt"
    assert parts[1] == "tenantC"
    assert parts[3] == "spatial_features"
    assert parts[4] == "5"
    assert parts[5] == "6"
    assert parts[6] == "20"
    assert parts[7] == "21"


@pytest.mark.django_db
def test_build_tile_cache_key_tenant_variation():
    rf = RequestFactory()
    base = {"META": {"HTTP_AUTHORIZATION": "Bearer tokSame"}}
    req1 = rf.get("/api/v1.0/mapping/tiles/7/30/31.pbf")
    req1.META.update(base["META"])
    req1.user = DummyUser("tenant1")
    req2 = rf.get("/api/v1.0/mapping/tiles/7/30/31.pbf")
    req2.META.update(base["META"])
    req2.user = DummyUser("tenant2")
    k1 = build_tile_cache_key(req1, 7, 30, 31, ["spatial_features"], cache_version="1")
    k2 = build_tile_cache_key(req2, 7, 30, 31, ["spatial_features"], cache_version="1")
    assert k1 != k2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "auth_header",
    [
        "",  # missing
        "Token something",  # wrong scheme
        "Bearer ",  # empty token
    ],
)
def test_build_tile_cache_key_invalid_auth(auth_header):
    rf = RequestFactory()
    req = rf.get("/api/v1.0/mapping/tiles/8/40/41.pbf")
    if auth_header:
        req.META["HTTP_AUTHORIZATION"] = auth_header
    req.user = DummyUser("tenantX")
    with pytest.raises(ValueError):
        build_tile_cache_key(req, 8, 40, 41, ["spatial_features"], cache_version="2")


@pytest.mark.django_db
@override_settings(VECTOR_TILE_CACHE_VERSION="9")
def test_tile_view_caching_and_authentication():
    rf = RequestFactory()
    view = SpatialFeatureTileView.as_view()

    # Missing token -> 401
    request_unauth = rf.get("/api/v1.0/mapping/tiles/10/100/200.pbf")
    response = view(request_unauth, z=10, x=100, y=200)
    assert response.status_code == 401

    # Authenticated request -> MISS then HIT
    auth_request = rf.get("/api/v1.0/mapping/tiles/10/100/200.pbf")
    auth_request.META["HTTP_AUTHORIZATION"] = "Bearer mytoken123"
    auth_request.user = DummyUser("tenantZZ")

    with patch("vectortiles.views.MVTView.get") as parent_get:
        parent_get.return_value = HttpResponse(b"tiledata", content_type="application/x-protobuf")
        cache.clear()
        first = view(auth_request, z=10, x=100, y=200)
        assert first.status_code == 200
        assert first["X-Cache"] == "MISS"
        second = view(auth_request, z=10, x=100, y=200)
        assert second.status_code == 200
        assert second["X-Cache"] == "HIT"
        assert parent_get.call_count == 1
        assert second.get("Vary") == "Authorization"


@pytest.mark.django_db
def test_tile_view_cache_version_changes_key():
    rf = RequestFactory()
    view = SpatialFeatureTileView.as_view()
    req1 = rf.get("/api/v1.0/mapping/tiles/3/4/5.pbf")
    req1.META["HTTP_AUTHORIZATION"] = "Bearer abc"
    req1.user = DummyUser("tenant1")
    req2 = rf.get("/api/v1.0/mapping/tiles/3/4/5.pbf")
    req2.META["HTTP_AUTHORIZATION"] = "Bearer abc"
    req2.user = DummyUser("tenant1")

    with override_settings(VECTOR_TILE_CACHE_VERSION="1"):
        with patch("vectortiles.views.MVTView.get") as parent_get:
            parent_get.return_value = HttpResponse(b"tile", content_type="application/x-protobuf")
            cache.clear()
            first = view(req1, z=3, x=4, y=5)
            assert first["X-Cache"] == "MISS"
    with override_settings(VECTOR_TILE_CACHE_VERSION="2"):
        with patch("vectortiles.views.MVTView.get") as parent_get2:
            parent_get2.return_value = HttpResponse(b"tile", content_type="application/x-protobuf")
            second = view(req2, z=3, x=4, y=5)
            assert second["X-Cache"] == "MISS"
            assert parent_get2.call_count == 1
