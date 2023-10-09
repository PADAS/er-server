import json
from unittest.mock import patch

import pytest

from django.http import HttpResponse
from django.urls import reverse

from client_http import HTTPClient
from utils.features import features
from utils.middleware import TenantSettingsMiddleware
from utils.tenant.thread import Tenant, get_tenant_settings


@pytest.mark.django_db
class TestTenantSettingsMiddleware:
    @pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    @patch("utils.tenant.providers.TenantData.get_tenant_data")
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
        assert json.loads(settings.to_json()) == tenant_response

    @pytest.mark.skipif(features.tms.is_on(), reason="TMS feature flag is on")
    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    def test_tenant_settings_middleware_getting_tenant_from_django(self, mocked_tenant_client, tenant_response, rf):
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
        assert json.loads(settings.to_json()) == tenant_response

    def _get_response(self, request):
        return HttpResponse()
