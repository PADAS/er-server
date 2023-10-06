import pytest

from utils.features import features
from utils.tenant import Tenant, get_tenant_settings
from utils.tenant.managers import TenantContextManager
from utils.tenant.thread import TENANT_DEFAULT_KEY, _get_local_thread


@pytest.mark.django_db
@pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
class TestTenantContextManager:
    def test_tenant_context_manager(self, memory_store_client_mock):
        main_thread = _get_local_thread()
        with TenantContextManager(domain="zoo.com"):
            memory_store_client_mock.get_key.assert_called_once()
            assert TENANT_DEFAULT_KEY in main_thread.__dict__.keys()
            assert isinstance(get_tenant_settings(), Tenant)

        # FixMe?: The test assumes that there was no previous Tenant set in the thread
        # It fails when there was a previous Tenant set
        assert TENANT_DEFAULT_KEY not in main_thread.__dict__.keys()

    @pytest.mark.parametrize("domain", ["", None])
    def test_tenant_context_manager_with_no_domain(self, domain, memory_store_client_mock):
        with pytest.raises(ValueError) as error:
            with TenantContextManager(domain=domain):
                pass

        assert "domain cannot be None or empty an string" in str(error)
