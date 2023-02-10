import pytest

from utils.features import features
from utils.tenant.thread import Tenant, get_tenant_settings, set_tenant_settings


class TestThreadStorage:
    @pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
    def test_set_tenant_dict_settings_in_main_thread(self, tenant_response):
        set_tenant_settings(tenant_response)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert tenant_response == settings.to_dict()
