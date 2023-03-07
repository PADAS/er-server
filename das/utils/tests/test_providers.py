import json
from unittest.mock import patch

import pytest

from utils.features import features
from utils.tenant.providers import TenantData


@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
class TestTenantData:
    instance = TenantData(domain="zoo.com")

    @patch("core.tms.HTTPClient.get_tenant_data")
    def test_get_data_from_tms(self, mock_client, tenant_response):
        mock_client.return_value = tenant_response

        tenant_data = self.instance.get()

        assert tenant_response == tenant_data

    @patch("utils.persistent.RedisStorage.get_key")
    def test_get_from_cache(self, mocked_redis, tenant_response):
        mocked_redis.return_value = json.dumps(tenant_response)

        tenant_data = self.instance.get()

        assert tenant_response == tenant_data

    @patch("core.tms.HTTPClient.get_tenant_data")
    def test_set_to_cache(self, mock_client, tenant_response):
        mock_client.return_value = tenant_response
        with patch("utils.persistent.RedisStorage.insert_key") as mocked_redis:
            self.instance._fetch_from_tms()
            mocked_redis.assert_called_once()

    @patch("utils.persistent.RedisStorage.get_key")
    def test_get_from_cache_malformed(self, mocked_redis):
        mocked_redis.return_value = "not-a-json"
        cached = self.instance._get_from_cache()
        assert cached is None
