import json
import logging

import pytest

from utils.features import features
from utils.tenant import TenantNotFoundException
from utils.tenant.providers import TenantData

DOMAIN = "zoo.com"


@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
class TestTenantData:
    instance = TenantData(domain=DOMAIN)

    def test_get_tenant_from_cache(self, memory_store_client_mock, tenant_response, caplog):
        caplog.set_level(logging.INFO)
        memory_store_client_mock.get_key.return_value = json.dumps(tenant_response)

        tenant_data = self.instance.get()

        assert tenant_data == tenant_response
        assert f"Getting tenant from cache for domain {DOMAIN}" in caplog.text
        assert f"Gotten tenant data in" in caplog.text
        assert "Tenant not found at cache" not in caplog.text

    def test_get_tenant_from_tms_passing_through_cache_first(
        self, memory_store_client_mock, tms_api_client_mock, tenant_response, caplog
    ):
        caplog.set_level(logging.INFO)
        memory_store_client_mock.get_key.return_value = None
        tms_api_client_mock.get_tenant_data.return_value = tenant_response

        tenant_data = self.instance.get()

        assert tenant_data == tenant_response
        assert f"Getting tenant from cache for domain {DOMAIN}" in caplog.text
        assert "Tenant not found at cache" in caplog.text
        assert f"Getting tenant from TMS for domain {DOMAIN}" in caplog.text

    def test_raise_tenant_not_found_exception(self, memory_store_client_mock, tms_api_client_mock, caplog):
        memory_store_client_mock.get_key.return_value = None
        tms_api_client_mock.get_tenant_data.return_value = None

        with pytest.raises(TenantNotFoundException):
            tenant_data = self.instance.get()

            assert tenant_data is None
            assert f"Getting tenant from cache for domain {DOMAIN}" in caplog.text
            assert "Tenant not found at cache" not in caplog.text
            assert f"Getting tenant from TMS for domain {DOMAIN}" in caplog.text
