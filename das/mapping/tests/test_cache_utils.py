"""Tests for mapping.cache build_tile_cache_key utility."""

import pytest

from django.test import RequestFactory

from mapping.cache import build_tile_cache_key


class DummyUser:
    def __init__(self, tenant_id="tenant123"):
        self.das_tenant_id = tenant_id


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
    request = _make_request(headers={"Authorization": "Bearer abc123"})
    key1 = build_tile_cache_key(request, 5, 10, 12, ["b", "a"])  # unsorted input
    key2 = build_tile_cache_key(request, 5, 10, 12, ["a", "b"])  # already sorted
    assert key1 == key2
    # Key: vt:{tenant}:{token_hash}:{layers}:{version}:{z}:{x}:{y}:{query_hash}
    parts = key1.split(":")
    assert parts[3] == "a,b"


def test_build_tile_cache_key_query_param_order_invariance():
    # same logical params, different submission order
    req1 = _make_request(headers={"Authorization": "Bearer tokenXYZ"}, params={"z": "1", "a": "2"})
    req2 = _make_request(headers={"Authorization": "Bearer tokenXYZ"}, params={"a": "2", "z": "1"})
    k1 = build_tile_cache_key(req1, 1, 2, 3, ["layer"])  # noqa: E741
    k2 = build_tile_cache_key(req2, 1, 2, 3, ["layer"])  # noqa: E741
    assert k1 == k2
    # query hash should not be 'noquery'
    assert not k1.endswith(":noquery")


def test_build_tile_cache_key_include_query_false_uses_noquery():
    request = _make_request(headers={"Authorization": "Bearer qwerty"}, params={"foo": "bar"})
    key = build_tile_cache_key(request, 2, 4, 8, ["x"], include_query=False)
    assert key.endswith(":noquery")


def test_build_tile_cache_key_token_hash_length():
    request = _make_request(headers={"Authorization": "Bearer supersecrettokenvalue"})
    key = build_tile_cache_key(request, 9, 1, 1, ["l"])
    # Key: vt:{tenant}:{token_hash}:{layers}:{version}:{z}:{x}:{y}:{query_hash}
    parts = key.split(":")
    token_hash = parts[2]
    assert len(token_hash) == 16


def test_build_tile_cache_key_missing_bearer_token_raises_value_error():
    request = _make_request(headers={"Authorization": "Token something"})  # wrong scheme
    with pytest.raises(ValueError):
        build_tile_cache_key(request, 0, 0, 0, ["l"])  # noqa: F841


def test_build_tile_cache_key_empty_layer_list_uses_nolayers():
    request = _make_request(headers={"Authorization": "Bearer abc"})
    key = build_tile_cache_key(request, 1, 1, 1, [])
    # Key: vt:{tenant}:{token_hash}:{layers}:{version}:{z}:{x}:{y}:{query_hash}
    parts = key.split(":")
    assert parts[3] == "nolayers"
