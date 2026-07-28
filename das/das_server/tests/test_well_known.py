"""Tests for the RFC 9728 protected-resource discovery endpoint.

The endpoint at ``/.well-known/oauth-protected-resource`` lets interactive
clients discover which authorization server(s) a site accepts, replacing the
ad-hoc discovery role that ``/api/v1.0/status`` used to serve.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from oauth2_provider.models import get_application_model
from oauth2_provider.settings import oauth2_settings

from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import APIClient

from utils.auth0.helpers import get_auth0_custom_domain
from utils.tenant import Tenant

Application = get_application_model()

PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"


def _expected_das_issuer() -> str:
    """The DAS-as-authorization-server issuer, derived exactly as DOT does.

    RFC 9728 lists authorization servers by their RFC 8414 issuer identifier.
    When DAS is the authorization server, that identifier is DOT's own OIDC
    issuer (served at ``/oauth2/.well-known/openid-configuration``), so the
    endpoint must advertise precisely that string.
    """
    return oauth2_settings.oidc_issuer(RequestFactory().get(PROTECTED_RESOURCE_PATH))


def _expected_auth0_issuer() -> str:
    return f"https://{get_auth0_custom_domain()}/"


def _tenant_with(tenant_response: dict, *, require_idp: bool) -> Tenant:
    tenant = Tenant.from_dict(tenant_response)
    tenant.feature_flags.require_idp = require_idp
    return tenant


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch", "tenant_document_cache_client_mock")
class TestOAuthProtectedResourceMetadata:
    def _pin_require_idp(self, monkeypatch, tenant_response, *, require_idp: bool) -> None:
        # TenantSettingsMiddleware repopulates the thread-local tenant on each request,
        # so control require_idp by patching the view's get_tenant_settings directly.
        monkeypatch.setattr(
            "das_server.well_known.get_tenant_settings",
            MagicMock(return_value=_tenant_with(tenant_response, require_idp=require_idp)),
        )

    def test_legacy_site_advertises_das_authorization_server_only(self, monkeypatch, tenant_response):
        self._pin_require_idp(monkeypatch, tenant_response, require_idp=False)

        response = APIClient().get(PROTECTED_RESOURCE_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["authorization_servers"] == [_expected_das_issuer()]

    def test_resource_echoes_the_request_origin(self, monkeypatch, tenant_response):
        # RFC 9728 s3.3: the resource value must equal the origin the metadata URL
        # was built from, or a conformant client discards the document.
        self._pin_require_idp(monkeypatch, tenant_response, require_idp=False)

        response = APIClient().get(PROTECTED_RESOURCE_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["resource"] == "http://testserver"

    def test_migrated_site_with_a_bypass_row_advertises_auth0_then_das(self, monkeypatch, tenant_response):
        self._pin_require_idp(monkeypatch, tenant_response, require_idp=True)
        Application.objects.filter(bypass_auth0=True).delete()
        Application.objects.create(client_id="legacy-still-bypassing", bypass_auth0=True)
        Application.objects.create(client_id="cutover-app", bypass_auth0=False)

        response = APIClient().get(PROTECTED_RESOURCE_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["authorization_servers"] == [_expected_auth0_issuer(), _expected_das_issuer()]

    def test_fully_migrated_site_advertises_auth0_only(self, monkeypatch, tenant_response):
        self._pin_require_idp(monkeypatch, tenant_response, require_idp=True)
        Application.objects.filter(bypass_auth0=True).delete()
        Application.objects.create(client_id="cutover-app", bypass_auth0=False)

        response = APIClient().get(PROTECTED_RESOURCE_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["authorization_servers"] == [_expected_auth0_issuer()]

    def test_response_is_publicly_cacheable_for_300_seconds(self, monkeypatch, tenant_response):
        self._pin_require_idp(monkeypatch, tenant_response, require_idp=False)

        response = APIClient().get(PROTECTED_RESOURCE_PATH)

        assert response.status_code == status.HTTP_200_OK
        directives = {directive.strip() for directive in response["Cache-Control"].split(",")}
        assert directives == {"max-age=300", "public"}

    def test_discovery_succeeds_without_authentication(self, monkeypatch, tenant_response):
        self._pin_require_idp(monkeypatch, tenant_response, require_idp=True)
        Application.objects.filter(bypass_auth0=True).delete()

        response = APIClient().get(PROTECTED_RESOURCE_PATH)

        assert response.status_code == status.HTTP_200_OK
