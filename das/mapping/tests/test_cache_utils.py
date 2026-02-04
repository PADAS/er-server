"""Tests for mapping.cache build_tile_cache_key utility."""

import pytest

from django.test import RequestFactory

from utils.cache import build_tile_cache_key


class DummyUser:
    def __init__(self, tenant_id="tenant123", user_id="user-1"):
        self.das_tenant_id = tenant_id
        self.id = user_id


def _make_request(path="/tiles/", headers=None, params=None, user=None):
    rf = RequestFactory()
    params = params or {}
    request = rf.get(path, data=params)
    headers = headers or {}
    for k, v in headers.items():
        http_key = k if k.startswith("HTTP_") else f"HTTP_{k.upper().replace('-','_')}"
        request.META[http_key] = v
    request.user = user or DummyUser()
    return request


def test_build_tile_cache_key_basic_order_invariance_layers():
    request = _make_request(headers={"HTTP_AUTHORIZATION": "Bearer abc123"})
    key1 = build_tile_cache_key(request, 5, 10, 12, ["b", "a"])  # unsorted input
    key2 = build_tile_cache_key(request, 5, 10, 12, ["a", "b"])  # already sorted
    assert key1 == key2
    # Key: vt:{tenant}:{layers}:{version}:{z}:{x}:{y}:{user_hash}:{query_hash}
    parts = key1.split(":")
    assert parts[0] == "vt"
    assert parts[1] == "tenant123"  # tenant
    assert parts[2] == "a,b"  # layers (sorted)
    assert parts[3] == "1"  # cache_version (default)
    assert parts[4] == "5"  # z
    assert parts[5] == "10"  # x
    assert parts[6] == "12"  # y
    assert len(parts[7]) == 8  # user hash


def test_build_tile_cache_key_query_param_order_invariance():
    # same logical params, different submission order
    req1 = _make_request(headers={"HTTP_AUTHORIZATION": "Bearer tokenXYZ"}, params={"z": "1", "a": "2"})
    req2 = _make_request(headers={"HTTP_AUTHORIZATION": "Bearer tokenXYZ"}, params={"a": "2", "z": "1"})
    k1 = build_tile_cache_key(req1, 1, 2, 3, ["layer"])  # noqa: E741
    k2 = build_tile_cache_key(req2, 1, 2, 3, ["layer"])  # noqa: E741
    assert k1 == k2
    # query hash should not be 'noquery'
    assert not k1.endswith(":noquery")


def test_build_tile_cache_key_include_query_false_uses_noquery():
    request = _make_request(headers={"HTTP_AUTHORIZATION": "Bearer qwerty"}, params={"foo": "bar"})
    key = build_tile_cache_key(request, 2, 4, 8, ["x"], include_query=False)
    assert key.endswith(":noquery")


def test_build_tile_cache_key_user_hash_length():
    request = _make_request(headers={"HTTP_AUTHORIZATION": "Bearer supersecrettokenvalue"})
    key = build_tile_cache_key(request, 9, 1, 1, ["l"])
    # Key: vt:{tenant}:{layers}:{version}:{z}:{x}:{y}:{user_hash}:{query_hash}
    parts = key.split(":")
    user_hash = parts[7]
    assert len(user_hash) == 8


def test_build_tile_cache_key_requires_user_and_tenant():
    # Missing user id
    class NoIdUser:
        def __init__(self):
            self.das_tenant_id = "tenant123"

    request_no_id = _make_request(user=NoIdUser())
    with pytest.raises(ValueError):
        build_tile_cache_key(request_no_id, 0, 0, 0, ["l"])  # noqa: F841

    # Missing tenant id
    class NoTenantUser:
        def __init__(self):
            self.id = "user-1"

    request_no_tenant = _make_request(user=NoTenantUser())
    with pytest.raises(ValueError):
        build_tile_cache_key(request_no_tenant, 0, 0, 0, ["l"])  # noqa: F841


def test_build_tile_cache_key_empty_layer_list_uses_nolayers():
    request = _make_request(headers={"HTTP_AUTHORIZATION": "Bearer abc"})
    key = build_tile_cache_key(request, 1, 1, 1, [])
    # Key: vt:{tenant}:{layers}:{version}:{z}:{x}:{y}:{user_hash}:{query_hash}
    parts = key.split(":")
    assert parts[0] == "vt"
    assert parts[1] == "tenant123"  # tenant
    assert parts[2] == "nolayers"  # empty layer list becomes 'nolayers'
    assert parts[3] == "1"  # cache_version (default)
    assert parts[4] == "1"  # z
    assert parts[5] == "1"  # x
    assert parts[6] == "1"  # y
    assert len(parts[7]) == 8  # user hash
