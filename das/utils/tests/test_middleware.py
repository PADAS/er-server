import json
import logging
from unittest.mock import patch

import pytest

from django.core.exceptions import DisallowedHost
from django.http import HttpResponse
from django.test import override_settings
from django.urls import reverse

from client_http import HTTPClient
from utils.features import features
from utils.middleware import TenantSettingsMiddleware
from utils.tenant.thread import Tenant, get_tenant_settings


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
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

    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    @patch("utils.tenant.domains.get_current_cluster_domains")
    @override_settings(ALLOWED_HOSTS=["testserver.org", "localhost"])
    def test_middleware_adds_valid_tenant(self, mocked_cluster_domains, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response
        mocked_cluster_domains.return_value = ["tenant.testserver.org"]
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url, HTTP_HOST="tenant.testserver.org")
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)

        from django.conf import settings

        assert request.get_host() in settings.ALLOWED_HOSTS

    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    @patch("utils.tenant.domains.get_current_cluster_domains")
    @override_settings(ALLOWED_HOSTS=["testserver.org", "tenant.testserver.org"])
    def test_middleware_ignores_known_tenant(self, mocked_cluster_domains, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response
        mocked_cluster_domains.return_value = ["tenant.testserver.org"]
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url, HTTP_HOST="tenant.testserver.org")
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)

        assert not mocked_cluster_domains.called

    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    @patch("utils.tenant.domains.get_current_cluster_domains")
    @override_settings(ALLOWED_HOSTS=["testserver.org", "test.testserver.org", "localhost"])
    def test_middleware_fails_with_invalid_tenant(
        self, mocked_cluster_domains, mocked_tenant_client, tenant_response, caplog, rf
    ):
        caplog.set_level(logging.INFO)
        mocked_tenant_client.return_value = tenant_response
        mocked_cluster_domains.return_value = ["tenant.testserver.org"]
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url, HTTP_HOST="not-a-tenant.testserver.org")
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        with pytest.raises(DisallowedHost):
            settings_middleware(request)

        from django.conf import settings

        assert "not-a-tenant.testserver.org" not in settings.ALLOWED_HOSTS

    def _get_response(self, request):
        return HttpResponse()
