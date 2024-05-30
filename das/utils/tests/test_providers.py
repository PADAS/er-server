import json
import logging
import os

import pytest

from utils.features import features
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.providers import TenantData, get_current_cluster_domains

DOMAIN = "zoo.com"


@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
class TestTenantData:
    instance = TenantData(domain=DOMAIN)

    def test_get_tenant_from_cache(self, memory_store_client_mock, tenant_response, caplog):
        caplog.set_level(logging.DEBUG)
        memory_store_client_mock.get_key.return_value = json.dumps(tenant_response)

        tenant_data = self.instance.get_tenant_data()

        assert tenant_data == tenant_response
        assert f"Getting tenant from cache for domain {DOMAIN}" in caplog.text
        assert f"Retrieved tenant data in" in caplog.text
        assert "Tenant not found at cache" not in caplog.text

    def test_get_tenant_from_tms_passing_through_cache_first(
        self, memory_store_client_mock, tms_api_client_mock, tenant_response, caplog
    ):
        caplog.set_level(logging.DEBUG)
        memory_store_client_mock.get_key.return_value = None
        tms_api_client_mock.get_tenant_data.return_value = tenant_response

        tenant_data = self.instance.get_tenant_data()

        assert tenant_data == tenant_response
        assert f"Getting tenant from cache for domain {DOMAIN}" in caplog.text
        assert f"Tenant {DOMAIN} not found in cache" in caplog.text
        assert f"Getting tenant from TMS for domain {DOMAIN}" in caplog.text

    def test_get_tenant_not_found(self, memory_store_client_mock, tms_api_client_mock, caplog):
        caplog.set_level(logging.DEBUG)
        memory_store_client_mock.get_key.return_value = None
        tms_api_client_mock.get_tenant_data.return_value = None
        tenant_data = None

        with pytest.raises(TenantNotFoundException):
            tenant_data = self.instance.get_tenant_data()

        assert tenant_data is None
        assert f"Getting tenant from cache for domain {DOMAIN}" in caplog.text
        assert f"Tenant {DOMAIN} not found in cache" in caplog.text
        assert f"Getting tenant from TMS for domain {DOMAIN}" in caplog.text
        assert f"Tenant not found in TMS for domain {DOMAIN}" in caplog.text

    @pytest.mark.parametrize(
        "data",
        [
            {"domains": [b"tenant_domain1.com", b"tenant_domain2.com"], "expected": 2},
            {"domains": [b"domain2.com", b"domain3.com", b"domain1.com"], "expected": 3},
            {"domains": [], "expected": 0},
        ],
    )
    def test_get_all_tenant_domains_from_cache(self, monkeypatch, data, memory_store_client_mock):
        monkeypatch.setitem(os.environ, "CLUSTER_NAME", "R2D2")
        monkeypatch.setitem(os.environ, "CLUSTER_NAMESPACE", "SPACE")
        memory_store_client_mock.get_set_by_key.return_value = data["domains"]

        domains = get_current_cluster_domains()

        assert data["expected"] == len(domains) - 1  # include the settings.SERVER_FQDN domain
        for domain in data["domains"]:
            assert domain.decode("utf-8") in domains
