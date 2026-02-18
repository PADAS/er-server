"""
Tests for Auth0 admin authentication integration.

This module tests the conditional Auth0 authentication for Django Admin
based on the tenant's require_idp feature flag using our session-based
implementation with Authlib OAuth client.
"""

import urllib.parse
from unittest.mock import Mock, patch

import pytest

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.auth0_admin import (
    admin_login_entrypoint,
    admin_logout,
    auth0_callback,
    initiate_auth0_admin_login,
)

User = get_user_model()


@pytest.fixture
def request_factory():
    """Create a Django request factory."""
    return RequestFactory()


@pytest.fixture
def mock_tenant_settings_require_idp_false():
    """Mock tenant settings with require_idp=False."""
    with patch("accounts.auth0_admin.get_tenant_settings") as mock_settings:
        mock = Mock()
        mock.feature_flags.require_idp = False
        mock_settings.return_value = mock
        yield mock


@pytest.fixture
def mock_tenant_settings_require_idp_true():
    """Mock tenant settings with require_idp=True."""
    with patch("accounts.auth0_admin.get_tenant_settings") as mock_settings:
        mock = Mock()
        mock.feature_flags.require_idp = True
        mock.feature_flags.idp_org_id = "org_test123"
        mock_settings.return_value = mock
        yield mock


@pytest.fixture
def mock_tenant_settings_require_idp_true_no_org():
    """Mock tenant settings with require_idp=True but no org_id."""
    with patch("accounts.auth0_admin.get_tenant_settings") as mock_settings:
        mock = Mock()
        mock.feature_flags.require_idp = True
        mock.feature_flags.idp_org_id = None
        mock_settings.return_value = mock
        yield mock


@pytest.fixture
def admin_user_with_auth0_id():
    """Create an admin user with auth0_id."""
    return User.objects.create_user(
        username="testadmin", email="admin@example.com", is_staff=True, is_active=True, auth0_id="auth0|123456789"
    )


@pytest.mark.django_db
class TestAdminLoginEntrypoint:
    """Test the admin_login_entrypoint function."""

    def test_require_idp_false_uses_django_admin(self, request_factory, mock_tenant_settings_require_idp_false):
        """Test that when require_idp=False, Django's default admin login is used."""
        request = request_factory.get("/admin/login/")

        with patch("accounts.auth0_admin.admin.site.login") as mock_admin_login:
            mock_admin_login.return_value = HttpResponse("django_admin_response")
            result = admin_login_entrypoint(request)

            mock_admin_login.assert_called_once_with(request)
            assert result.content == b"django_admin_response"

    def test_require_idp_true_redirects_to_auth0(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that when require_idp=True, user is redirected to Auth0 login."""
        request = request_factory.get("/admin/login/?next=/admin/some/page")

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        expected_location = f"{reverse('auth0_admin_login')}?next=/admin/some/page&org_id=org_test123"
        assert result.url == expected_location

    def test_preserves_next_parameter(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that the next parameter is properly preserved in Auth0 flow."""
        request = request_factory.get("/admin/login/?next=/admin/custom/path")

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert "next=/admin/custom/path" in result.url
        assert "org_id=org_test123" in result.url

    def test_require_idp_true_no_org_id_uses_django_admin(
        self, request_factory, mock_tenant_settings_require_idp_true_no_org
    ):
        """Test that when require_idp=True but org_id is None, Django admin is used."""
        request = request_factory.get("/admin/login/")

        with patch("accounts.auth0_admin.admin.site.login") as mock_admin_login:
            mock_admin_login.return_value = HttpResponse("django_admin_response")
            result = admin_login_entrypoint(request)

            mock_admin_login.assert_called_once_with(request)
            assert result.content == b"django_admin_response"

    def test_handles_tenant_settings_error(self, request_factory):
        """Test that tenant settings errors fall back to Django admin login."""
        request = request_factory.get("/admin/login/")

        with patch("accounts.auth0_admin.get_tenant_settings", side_effect=Exception("Tenant error")):
            with patch("accounts.auth0_admin.admin.site.login") as mock_admin_login:
                mock_admin_login.return_value = HttpResponse("fallback_response")
                result = admin_login_entrypoint(request)

                mock_admin_login.assert_called_once_with(request)
                assert result.content == b"fallback_response"

    def test_default_next_parameter(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that missing next parameter defaults to /admin/."""
        request = request_factory.get("/admin/login/")
        request.user = AnonymousUser()

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert "next=/admin/" in result.url
        assert "org_id=org_test123" in result.url

    def test_authenticated_staff_user_skips_auth0_and_sets_efb_cookie(
        self, request_factory, mock_tenant_settings_require_idp_true, admin_user_with_auth0_id
    ):
        """When require_idp=True and user is already authenticated, skip Auth0 and set EFB cookie."""
        request = request_factory.get("/admin/login/?next=/admin/form-builder/")
        request.user = admin_user_with_auth0_id

        with patch("accounts.auth0_admin.set_efb_token_cookie") as mock_set_cookie:
            result = admin_login_entrypoint(request)

            assert result.status_code == 302
            assert result.url == "/admin/form-builder/"
            mock_set_cookie.assert_called_once_with(request, result)

    def test_authenticated_staff_user_default_next(
        self, request_factory, mock_tenant_settings_require_idp_true, admin_user_with_auth0_id
    ):
        """When no next parameter, authenticated user redirects to /admin/."""
        request = request_factory.get("/admin/login/")
        request.user = admin_user_with_auth0_id

        with patch("accounts.auth0_admin.set_efb_token_cookie"):
            result = admin_login_entrypoint(request)

            assert result.status_code == 302
            assert result.url == "/admin/"

    def test_authenticated_non_staff_user_redirects_to_auth0(
        self, request_factory, mock_tenant_settings_require_idp_true
    ):
        """When require_idp=True and user is authenticated but not staff, redirect to Auth0."""
        non_staff_user = User.objects.create_user(
            username="regularuser", email="regular@example.com", is_staff=False, is_active=True
        )
        request = request_factory.get("/admin/login/?next=/admin/")
        request.user = non_staff_user

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert reverse("auth0_admin_login") in result.url

    def test_unauthenticated_user_redirects_to_auth0(self, request_factory, mock_tenant_settings_require_idp_true):
        """When require_idp=True and user is not authenticated, redirect to Auth0."""
        request = request_factory.get("/admin/login/?next=/admin/form-builder/")
        request.user = AnonymousUser()

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert reverse("auth0_admin_login") in result.url
        assert "next=/admin/form-builder/" in result.url


@pytest.mark.django_db
class TestInitiateAuth0AdminLogin:
    """Test the initiate_auth0_admin_login function."""

    def test_stores_next_in_session(self, request_factory):
        """Test that next parameter is stored in session."""
        request = request_factory.get("/auth/admin-login/?next=/admin/target&org_id=org_test123")
        request.session = {}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            _ = initiate_auth0_admin_login(request)

            assert request.session["auth0_admin_next"] == "/admin/target"

    def test_default_next_in_session(self, request_factory):
        """Test that missing next parameter defaults to /admin/ in session."""
        request = request_factory.get("/auth/admin-login/?org_id=org_test123")
        request.session = {}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            _ = initiate_auth0_admin_login(request)

            assert request.session["auth0_admin_next"] == "/admin/"

    def test_calls_authlib_oauth_redirect_with_organization(self, request_factory):
        """Test that Authlib OAuth redirect is called with correct parameters including organization."""
        request = request_factory.get("/auth/admin-login/?org_id=org_test123")
        request.session = {}
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            _ = initiate_auth0_admin_login(request)

            mock_redirect.assert_called_once()
            call_args = mock_redirect.call_args
            assert call_args[0][0] == request  # First arg is request
            assert call_args[0][1] == "https://example.com/auth/callback/"  # Second arg is callback URL
            # Check that organization parameter is passed
            assert call_args[1]["organization"] == "org_test123"

    def test_missing_org_id_parameter(self, request_factory):
        """Test that missing org_id parameter passes None as organization."""
        request = request_factory.get("/auth/admin-login/")
        request.session = {}
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            _ = initiate_auth0_admin_login(request)

            mock_redirect.assert_called_once()
            call_args = mock_redirect.call_args
            assert call_args[0][0] == request  # First arg is request
            assert call_args[0][1] == "https://example.com/auth/callback/"  # Second arg is callback URL
            # Check that organization parameter is None when org_id missing
            assert call_args[1]["organization"] is None


@pytest.mark.django_db
class TestAuth0Callback:
    """Test the auth0_callback function."""

    def test_successful_authentication_and_redirect(self, request_factory, admin_user_with_auth0_id):
        """Test successful Auth0 callback flow."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/target"}

        mock_token = Mock()
        mock_token.get.return_value = {"sub": "auth0|123456789", "email": "admin@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin._auth0_admin_backend.authenticate") as mock_authenticate:
                with patch("accounts.auth0_admin.login") as mock_login:
                    with patch("accounts.auth0_admin.set_efb_token_cookie") as mock_set_efb_cookie:

                        mock_token_exchange.return_value = mock_token
                        mock_authenticate.return_value = admin_user_with_auth0_id

                        result = auth0_callback(request)

                        mock_token_exchange.assert_called_once_with(request)

                        mock_authenticate.assert_called_once_with(request, token=mock_token)

                        mock_login.assert_called_once_with(
                            request, admin_user_with_auth0_id, backend="accounts.backends.Auth0BackendForStaffUsers"
                        )

                        mock_set_efb_cookie.assert_called_once_with(request, result)

                        assert result.status_code == 302
                        assert result.url == "/admin/target"

                        assert "auth0_admin_next" not in request.session

    def test_authentication_failure_returns_403(self, request_factory):
        """Test that authentication failure returns 403."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        mock_token = Mock()

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin._auth0_admin_backend.authenticate") as mock_authenticate:

                mock_token_exchange.return_value = mock_token
                mock_authenticate.return_value = None  # Authentication fails

                result = auth0_callback(request)

                assert result.status_code == 403
                assert b"Authentication failed - insufficient privileges" in result.content

    def test_token_exchange_exception_returns_500(self, request_factory):
        """Test that token exchange exceptions return 500."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            mock_token_exchange.side_effect = Exception("Token exchange failed")

            result = auth0_callback(request)

            assert result.status_code == 500
            assert b"Authentication error" in result.content

    def test_default_redirect_when_no_session_next(self, request_factory, admin_user_with_auth0_id):
        """Test that missing session next parameter defaults to /admin/."""
        request = request_factory.get("/auth/callback/")
        request.session = {}  # No auth0_admin_next in session

        mock_token = Mock()
        mock_token.get.return_value = {"sub": "auth0|123456789", "email": "admin@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin._auth0_admin_backend.authenticate") as mock_authenticate:
                with patch("accounts.auth0_admin.login"):

                    mock_token_exchange.return_value = mock_token
                    mock_authenticate.return_value = admin_user_with_auth0_id

                    result = auth0_callback(request)

                    assert result.status_code == 302
                    assert result.url == "/admin/"


@pytest.mark.django_db
class TestAdminLogout:
    """Test the admin_logout function."""

    def test_require_idp_true_redirects_to_auth0_logout(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that when require_idp=True, user is redirected to Auth0 logout URL."""
        request = request_factory.get("/admin/logout/")
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.auth0_admin.django_logout") as mock_django_logout:
            with patch("accounts.auth0_admin.settings") as mock_settings:
                mock_settings.AUTH0_CUSTOM_DOMAIN = "test-tenant.auth0.com"
                mock_settings.AUTH0_CLIENT_ID_FOR_DJANGO_ADMIN = "test_client_id_123"

                result = admin_logout(request)

                # Verify django_logout was called
                mock_django_logout.assert_called_once_with(request)

                # Verify redirect to Auth0 logout URL
                assert result.status_code == 302
                assert "test-tenant.auth0.com/v2/logout" in result.url
                assert "client_id=test_client_id_123" in result.url
                # Verify returnTo parameter is URL encoded
                assert "returnTo=" in result.url

    def test_require_idp_false_redirects_to_admin_index(self, request_factory, mock_tenant_settings_require_idp_false):
        """Test that when require_idp=False, user is redirected to admin index."""
        request = request_factory.get("/admin/logout/")

        with patch("accounts.auth0_admin.django_logout") as mock_django_logout:
            result = admin_logout(request)

            # Verify django_logout was called
            mock_django_logout.assert_called_once_with(request)

            # Verify redirect to admin index
            assert result.status_code == 302
            assert result.url == reverse("admin:index")

    def test_handles_tenant_settings_error(self, request_factory):
        """Test that tenant settings errors redirect to admin index."""
        request = request_factory.get("/admin/logout/")

        with patch("accounts.auth0_admin.django_logout") as mock_django_logout:
            with patch("accounts.auth0_admin.get_tenant_settings", side_effect=Exception("Tenant error")):
                result = admin_logout(request)

                # Verify django_logout was called even on error
                mock_django_logout.assert_called_once_with(request)

                # Verify redirect to admin index on error
                assert result.status_code == 302
                assert result.url == reverse("admin:index")

    def test_auth0_logout_url_construction(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that Auth0 logout URL is constructed correctly with proper URL encoding."""
        request = request_factory.get("/admin/logout/")
        admin_index_url = reverse("admin:index")
        return_to_url = f"https://example.com{admin_index_url}"
        request.build_absolute_uri = lambda path: return_to_url

        with patch("accounts.auth0_admin.django_logout"):
            with patch("accounts.auth0_admin.settings") as mock_settings:
                mock_settings.AUTH0_CUSTOM_DOMAIN = "custom.auth0.com"
                mock_settings.AUTH0_CLIENT_ID_FOR_DJANGO_ADMIN = "admin_client_456"

                result = admin_logout(request)

                assert result.status_code == 302
                # Verify all components of the Auth0 logout URL
                assert "https://custom.auth0.com/v2/logout?" in result.url
                assert "client_id=admin_client_456" in result.url
                # The returnTo should be URL encoded
                expected_encoded_return = urllib.parse.quote_plus(return_to_url)
                assert f"returnTo={expected_encoded_return}" in result.url

    def test_django_logout_always_called(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that django_logout is always called regardless of require_idp setting."""
        request = request_factory.get("/admin/logout/")
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.auth0_admin.django_logout") as mock_django_logout:
            with patch("accounts.auth0_admin.settings") as mock_settings:
                mock_settings.AUTH0_CUSTOM_DOMAIN = "test.auth0.com"
                mock_settings.AUTH0_CLIENT_ID_FOR_DJANGO_ADMIN = "test_client"

                _ = admin_logout(request)

                # Verify django_logout was called
                mock_django_logout.assert_called_once_with(request)
