import threading

import pytest

from utils.features import features
from utils.tenant.thread import (
    TENANT_DEFAULT_KEY,
    Tenant,
    clear_tenant_settings,
    get_tenant_settings,
    set_tenant_settings,
)


@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
class TestThreadStorage:
    def test_set_tenant_dict_settings_in_main_thread(self, tenant_response):
        set_tenant_settings(tenant_response)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert tenant_response == settings.to_dict()

    def test_delete_tenant_dict_settings_in_main_thread(self, tenant_response):
        set_tenant_settings(tenant_response)
        main_thread = threading.main_thread()

        assert TENANT_DEFAULT_KEY in main_thread.__dict__.keys()

        clear_tenant_settings()

        assert TENANT_DEFAULT_KEY not in main_thread.__dict__.keys()
