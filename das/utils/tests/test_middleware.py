import logging
from unittest.mock import patch

import pytest

from django.http import HttpResponse
from django.urls import reverse

from client_http import HTTPClient
from utils.features import features
from utils.middleware import MultiTenantMiddleware, TenantSettingsMiddleware
from utils.tenant.thread import Tenant, get_tenant_settings


@pytest.mark.django_db
@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
class TestTenantSettingsMiddleware:
    @patch("utils.tenant.providers.TenantData.get")
    def test_tenant_settings_middleware_getting_tenant(self, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response

        client = HTTPClient()
        user = client.app_user

        url = f"{reverse('events')}"
        request = rf.get(url)
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert settings.to_dict() == tenant_response

    def _get_response(self, request):
        return HttpResponse()


@pytest.mark.django_db
class TestMultiTenantMiddleware:
    @pytest.mark.skip(reason="TMS feature flag is on")
    def test_multi_tenant_middleware(self, caplog, rf):
        caplog.set_level(logging.INFO)
        client = HTTPClient()
        user = client.app_user
        request = rf.get("/api/v1.0/status")
        request.user = user

        multi_tenant_middleware = MultiTenantMiddleware(self._get_response)
        multi_tenant_middleware(request)

        assert "Setting tenant localhost object at request." in caplog.text

    def _get_response(self, request):
        return HttpResponse()
