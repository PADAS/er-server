from unittest.mock import MagicMock

import pytest

from utils.persistent import MultitenantRedisStorage
from utils.tenant.cache import MultitenantRedisClient, make_cache_key
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException
from utils.tenant.thread import clear_tenant_settings


@pytest.fixture
def redis_connection_mock(monkeypatch):
    connection_mock = MagicMock()
    redis_mock = MagicMock()
    redis_mock.Redis.return_value = connection_mock
    monkeypatch.setattr("utils.persistent.redis", redis_mock)

    return connection_mock


class TestCache:
    def test_make_cache_key_with_tenant_id(self, tenant_settings):
        key = make_cache_key("the-key", "test", "v1")

        assert key == f"{tenant_settings.id}:test:v1:the-key"

    def test_make_cache_key_without_tenant_id(self):
        clear_tenant_settings()
        with pytest.raises(TenantNotFoundInLocalThreadException):
            make_cache_key("the-key", "test", "v1")

    def test_get_decorated_tenant_cache_keys_with_tenant_set(self, tenant_settings, redis_connection_mock):
        cache_mock = MultitenantRedisStorage(config=MagicMock())
        expected_key = f"{tenant_settings.id}:None:None:test-key"

        cache_mock.insert_key("test-key", "test-value", ttl=60)

        redis_connection_mock.set.assert_called_once_with(expected_key, "test-value", 60)

    def test_get_decorated_tenant_cache_keys_without_tenant_set(self, redis_connection_mock, caplog):
        clear_tenant_settings()
        cache_mock = MultitenantRedisStorage(config=MagicMock())

        with pytest.raises(TenantNotFoundInLocalThreadException):
            cache_mock.insert_key("test-key", "test-value", ttl=60)

        assert not redis_connection_mock.set.called
        assert "Could not add tenant ID as cache key prefix" in caplog.text


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
