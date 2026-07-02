from unittest.mock import MagicMock

import pytest

from django.conf import settings
from django.core.cache import caches

from utils.cache import (
    bump_scoped_tile_version,
    get_scoped_tile_version,
    get_vector_tile_cache,
)
from utils.persistent import MultitenantRedisStorage
from utils.tenant.cache import MultitenantRedisClient, make_cache_key
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException


@pytest.fixture
def redis_connection_mock(monkeypatch):
    connection_mock = MagicMock()
    redis_mock = MagicMock()
    redis_mock.Redis.return_value = connection_mock
    monkeypatch.setattr("utils.redis.redis", redis_mock)

    return connection_mock


class TestCache:
    def test_make_cache_key_with_tenant_id(self, tenant_settings):
        key = make_cache_key("the-key", "test", "v1")

        assert key == f"{tenant_settings.id}:test:v1:the-key"

    def test_get_decorated_tenant_cache_keys_with_tenant_set(self, tenant_settings, redis_connection_mock):
        cache_mock = MultitenantRedisStorage(config=MagicMock())
        expected_key = f"{tenant_settings.id}:None:None:test-key"

        cache_mock.insert_key("test-key", "test-value", ttl=60)

        redis_connection_mock.set.assert_called_once_with(expected_key, "test-value", 60)

    def test_access_to_different_values_using_same_key(self):
        default_cache = caches["default"]
        shared_cache = caches[settings.SHARED_CACHE_ALIAS]

        key = "key-a"
        shared_cache.set(key, "value-a")
        default_cache.set(key, "other-value-a")

        assert shared_cache.get(key) == "value-a"
        assert default_cache.get(key) == "other-value-a"


class TestMultitenantRedisClient:
    def test_multitenant_cache_client_with_tenant_set(self, monkeypatch, tenant_settings):
        monkeypatch.setattr("utils.tenant.cache.redis", MagicMock())
        client = MultitenantRedisClient("test-redis")

        client.get("value-name")

        client._redis.get.assert_called_once_with(f"{tenant_settings.id}:None:None:value-name")

    def test_multitenant_cache_client_with_tenant_unset(self, monkeypatch):
        make_cache_key_mock = MagicMock(side_effect=TenantNotFoundInLocalThreadException)
        monkeypatch.setattr("utils.tenant.cache.redis", MagicMock())
        monkeypatch.setattr("utils.tenant.cache.make_cache_key", make_cache_key_mock)
        client = MultitenantRedisClient("test-redis")

        with pytest.raises(TenantNotFoundInLocalThreadException):
            client.get("value-name")

        assert not client._redis.get.called


class TestScopedTileVersion:
    """The generic, app-agnostic scoped tile-version counter primitive."""

    @pytest.fixture(autouse=True)
    def _clear_vector_tile_cache(self):
        get_vector_tile_cache().clear()
        yield
        get_vector_tile_cache().clear()

    def test_unbumped_version_is_zero(self):
        assert get_scoped_tile_version("prefix_a", "x", "y") == 0

    def test_bump_increments_version(self):
        bump_scoped_tile_version("prefix_b", "x")
        assert get_scoped_tile_version("prefix_b", "x") == 1
        bump_scoped_tile_version("prefix_b", "x")
        assert get_scoped_tile_version("prefix_b", "x") == 2

    def test_versions_isolated_by_prefix_and_key_parts(self):
        bump_scoped_tile_version("prefix_c", "a")
        assert get_scoped_tile_version("prefix_c", "a") == 1
        # Different key parts under the same prefix are independent.
        assert get_scoped_tile_version("prefix_c", "b") == 0
        # Different prefix, same key parts, is independent.
        assert get_scoped_tile_version("prefix_d", "a") == 0

    def test_multiple_key_parts_compose_into_key(self):
        bump_scoped_tile_version("prefix_e", "tenant1", "user1")
        assert get_scoped_tile_version("prefix_e", "tenant1", "user1") == 1
        assert get_scoped_tile_version("prefix_e", "tenant1", "user2") == 0
