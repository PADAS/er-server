from unittest.mock import MagicMock

import pytest

from django.http import HttpResponse
from django.urls import reverse

from client_http import HTTPClient
from utils import middleware
from utils.features import features
from utils.tenant.thread import Tenant, get_tenant_settings


@pytest.mark.django_db
class TestTenantSettingsMiddleware:
    @pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
    def test_tenant_settings_middleware_getting_tenant(self, tenant_response, rf, monkeypatch):
        mock = MagicMock(return_value=tenant_response)
        monkeypatch.setattr("core.tenant.HTTPClient.get_tenant_data", mock)

        client = HTTPClient()
        user = client.app_user

        url = f"{reverse('events')}"
        request = rf.get(url)
        request.user = user

        settings_middleware = middleware.TenantSettingsMiddleware(self.get_response)
        settings_middleware(request)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert settings.to_dict() == tenant_response

    def get_response(self, request):
        return HttpResponse()
