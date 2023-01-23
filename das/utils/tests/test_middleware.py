from unittest.mock import patch

import pytest

from django.http import HttpResponse
from django.urls import reverse

from client_http import HTTPClient
from utils.features import features
from utils.middleware import TenantSettingsMiddleware
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
