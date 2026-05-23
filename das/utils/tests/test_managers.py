from unittest.mock import patch

import pytest

from django.test import RequestFactory, override_settings

from utils.features import features
from utils.tenant.exceptions import (
    TenantNotFoundException,
    TenantNotFoundInLocalThreadException,
)
from utils.tenant.managers import TenantContextManager, set_tenant_by_request


@pytest.mark.django_db
@pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
class TestTenantContextManager:
    @patch("utils.tenant.managers.TenantData")
    @patch("utils.tenant.managers.clear_tenant_settings")
    @patch("utils.tenant.managers.set_tenant_settings")
    @patch("utils.tenant.managers.get_tenant_settings")
    @patch("utils.tenant.managers.set_current_tenant")
    @patch("utils.tenant.managers.get_current_tenant")
    def test_tenant_context_manager_without_previous_tenant(
        self,
        get_current_tenant_mock,
        set_current_tenant_mock,
        get_tenant_settings_mock,
        set_tenant_settings_mock,
        clear_tenant_settings_mock,
        tenant_data_mock,
        tenant_response,
        das_tenant,
    ):
        get_tenant_settings_mock.side_effect = TenantNotFoundInLocalThreadException
        get_current_tenant_mock.return_value = None
        tenant_data_mock.return_value.get_tenant_data.return_value = tenant_response

        with TenantContextManager(domain="zoo.com"):
            pass

        assert get_tenant_settings_mock.called
        assert get_current_tenant_mock.called
        tenant_data_mock.assert_called_with(domain="zoo.com")
        tenant_data_mock.return_value.get_tenant_data.assert_called_once()
        set_tenant_settings_mock.assert_called_once()
        set_tenant_settings_mock.assert_called_with(value=tenant_response)
        clear_tenant_settings_mock.assert_called_once()

    @pytest.mark.parametrize("domain", ["", None])
    def test_tenant_context_manager_with_no_domain(self, domain, tenant_document_cache_client_mock):
        with pytest.raises(ValueError) as error:
            with TenantContextManager(domain=domain):
                pass

        assert "domain cannot be None or empty an string" in str(error)


@pytest.mark.django_db
class TestSetTenantByRequest:
    """Regression tests for the path that resolves a tenant from request.Host.

    Public, unauthenticated endpoints (community input) are mounted under a
    URL-path scope but tenant resolution still happens via the Host header.
    These tests lock the contract that an unknown host cannot slip past
    set_tenant_by_request — the only way a host gets through is by resolving
    to a real tenant via TenantData / get_tenant_data_by_host.
    """

    @override_settings(ALLOWED_HOSTS=["*"])
    @patch("utils.tenant.managers.set_tenant_data")
    @patch("utils.tenant.managers.get_tenant_data_by_host")
    def test_host_with_no_tenant_raises_tenant_not_found(self, get_tenant_data_by_host_mock, set_tenant_data_mock):
        get_tenant_data_by_host_mock.side_effect = TenantNotFoundException(domain="evil.example.com")
        request = RequestFactory().get("/api/v2.0/community/foo/", HTTP_HOST="evil.example.com")

        with pytest.raises(TenantNotFoundException):
            set_tenant_by_request(request=request)

        assert not set_tenant_data_mock.called

    @override_settings(ALLOWED_HOSTS=["*"])
    @patch("utils.tenant.managers.set_tenant_data")
    @patch("utils.tenant.managers.get_tenant_data_by_host")
    def test_known_host_resolves_tenant(self, get_tenant_data_by_host_mock, set_tenant_data_mock, tenant_response):
        get_tenant_data_by_host_mock.return_value = tenant_response
        request = RequestFactory().get("/api/v2.0/community/foo/", HTTP_HOST="zoo.com")

        set_tenant_by_request(request=request)

        get_tenant_data_by_host_mock.assert_called_with("zoo.com")
        set_tenant_data_mock.assert_called_once_with(tenant_response)
