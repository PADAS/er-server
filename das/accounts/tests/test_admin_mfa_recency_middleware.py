"""Tests for the admin MFA recency middleware."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.auth0_admin import INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME
from accounts.middleware import AdminMfaRecencyMiddleware

_VIEW_RESPONSE = HttpResponse("view-response")


def _build_middleware():
    """Middleware whose downstream get_response returns a recognizable sentinel."""
    return AdminMfaRecencyMiddleware(lambda request: _VIEW_RESPONSE)


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def mfa_site():
    """Tenant flags for a require_idp + require_mfa site with a 1-hour recency window."""
    with patch("accounts.middleware.get_tenant_settings") as mock_settings:
        flags = mock_settings.return_value.feature_flags
        flags.require_idp = True
        flags.require_mfa = True
        flags.mfa_max_age_seconds = 3600
        yield mock_settings


class TestAdminMfaRecencyMiddleware:
    def _request(self, request_factory, path, session):
        request = request_factory.get(path)
        request.session = session
        return request

    def test_absent_mfa_time_redirects_to_auth0_initiator(self, request_factory, mfa_site):
        request = self._request(request_factory, "/admin/", session={})
        response = _build_middleware()(request)
        assert response.status_code == 302
        assert reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME) in response.url
        assert "next=%2Fadmin%2F" in response.url

    def test_stale_mfa_time_redirects_to_auth0_initiator(self, request_factory, mfa_site):
        stale = {"admin_mfa_time": int(time.time()) - 7200}  # older than the 3600s window
        request = self._request(request_factory, "/admin/", session=stale)
        response = _build_middleware()(request)
        assert response.status_code == 302
        assert reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME) in response.url

    def test_fresh_mfa_time_passes_through(self, request_factory, mfa_site):
        fresh = {"admin_mfa_time": int(time.time()) - 10}
        request = self._request(request_factory, "/admin/", session=fresh)
        response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE

    def test_logout_endpoint_is_exempt(self, request_factory, mfa_site):
        # A stale/absent session must still be able to reach logout, or the user is trapped.
        request = self._request(request_factory, "/admin/logout/", session={})
        response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE

    def test_login_endpoint_is_exempt(self, request_factory, mfa_site):
        request = self._request(request_factory, "/admin/login/", session={})
        response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE

    def test_no_check_when_require_mfa_false(self, request_factory):
        with patch("accounts.middleware.get_tenant_settings") as mock_settings:
            flags = mock_settings.return_value.feature_flags
            flags.require_idp = True
            flags.require_mfa = False
            request = self._request(request_factory, "/admin/", session={})
            response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE

    def test_no_check_when_require_idp_false(self, request_factory):
        # require_mfa alone must not gate a non-IdP tenant, whose sessions are never Auth0-seeded.
        with patch("accounts.middleware.get_tenant_settings") as mock_settings:
            flags = mock_settings.return_value.feature_flags
            flags.require_idp = False
            flags.require_mfa = True
            request = self._request(request_factory, "/admin/", session={})
            response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE

    def test_non_admin_path_passes_through(self, request_factory, mfa_site):
        request = self._request(request_factory, "/api/v1.0/status/", session={})
        response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE

    def test_passes_through_when_tenant_settings_unavailable(self, request_factory):
        # On a guarded admin path, if tenant settings can't be resolved the middleware fails open
        # to the normal request flow (does not redirect), rather than blocking all admin access.
        with patch("accounts.middleware.get_tenant_settings", side_effect=Exception("no tenant")):
            request = self._request(request_factory, "/admin/", session={})
            response = _build_middleware()(request)
        assert response is _VIEW_RESPONSE
