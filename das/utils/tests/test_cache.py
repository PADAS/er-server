import pytest

from utils.features import features
from utils.tenant.cache import make_cache_key
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException
from utils.tenant.thread import clear_tenant_settings, set_tenant_settings


@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
class TestCache:
    def test_make_cache_key_with_tenant_id(self, tenant_response):
        set_tenant_settings(tenant_response)
        key = make_cache_key("the-key", "test", "v1")
        clear_tenant_settings()

        assert key == f"{tenant_response['id']}:test:v1:the-key"

    def test_make_cache_key_without_tenant_id(self):
        with pytest.raises(TenantNotFoundInLocalThreadException):
            make_cache_key("the-key", "test", "v1")
