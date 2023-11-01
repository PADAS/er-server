from random import choice
from unittest.mock import MagicMock

import pytest
from corsheaders.middleware import CorsMiddleware

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from utils.tenant.cors import (
    build_http_urls_from_domains,
    get_das_tenant_urls,
    get_tenant_aware_cors_allowed_origins,
)
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException


def get_response(request):
    return HttpResponse()


@pytest.mark.django_db
class TestTenantCorsMiddlewareSignal:
    @override_settings(CORS_ORIGIN_WHITELIST=[], CORS_ALLOW_ALL_ORIGINS=False)
    def test_cors_accepts_origin_from_das_tenant(self, five_tenants):
        tenant = five_tenants[0]
        request = RequestFactory().get("/", headers={"origin": f"https://{tenant.domain}"})
        request.META["HTTP_ORIGIN"] = f"https://{tenant.domain}"
        middleware = CorsMiddleware(get_response)

        response = middleware(request)

        assert response.headers["Access-Control-Allow-Origin"] == f"https://{tenant.domain}"

    @override_settings(CORS_ORIGIN_WHITELIST=["http://localhost"], CORS_ALLOW_ALL_ORIGINS=False)
    @pytest.mark.usefixtures("five_tenants")
    def test_cors_rejects_unknown_origin(self, monkeypatch):
        tenant_data_mock = MagicMock()
        tenant_data_mock.return_value.get_tenant_data.side_effect = TenantNotFoundInLocalThreadException
        monkeypatch.setattr("core.signals.TenantData", tenant_data_mock)
        middleware = CorsMiddleware(get_response)
        request = RequestFactory().get("/", headers={"origin": "https://somewhere-else.pamdas.org"})
        request.META["HTTP_ORIGIN"] = "https://somewhere-else.pamdas.org"

        response = middleware(request)

        assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.django_db
class TestTenantCors:
    def test_build_urls_from_domains(self):
        domains = "foo.pamdas.org"

        urls = list(build_http_urls_from_domains([domains]))

        assert len(urls) == 2
        assert "http://foo.pamdas.org" in urls
        assert "https://foo.pamdas.org" in urls

    def test_get_das_tenant_urls(self, monkeypatch, five_tenants):
        get_tenant_domains_mock = MagicMock()
        get_tenant_domains_mock.return_value = [t.domain for t in five_tenants]
        monkeypatch.setattr("utils.tenant.cors.get_current_cluster_domains", get_tenant_domains_mock)
        tenant = five_tenants[0]

        urls = get_das_tenant_urls()

        assert f"http://{tenant.domain}" in urls
        assert f"https://{tenant.domain}" in urls

    @override_settings(CORS_ORIGIN_WHITELIST=["http://localhost", "https://localhost"])
    def test_get_tenant_aware_cors_allowed_origins(self, monkeypatch, five_tenants):
        tenant = choice(five_tenants)
        get_tenant_domains_mock = MagicMock()
        get_tenant_domains_mock.return_value = [t.domain for t in five_tenants]
        monkeypatch.setattr("utils.tenant.cors.get_current_cluster_domains", get_tenant_domains_mock)

        cors_origins = get_tenant_aware_cors_allowed_origins()

        assert "http://localhost" in cors_origins
        assert "https://localhost" in cors_origins
        assert f"http://{tenant.domain}" in cors_origins
        assert f"https://{tenant.domain}" in cors_origins
