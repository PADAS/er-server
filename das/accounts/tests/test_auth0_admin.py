"""
Tests for Auth0 admin authentication integration.

This module tests the conditional Auth0 authentication for Django Admin
based on the tenant's require_idp feature flag using our session-based
implementation with Authlib OAuth client.
"""

import urllib.parse
from unittest.mock import Mock, patch

import pytest
from django_multitenant.utils import set_current_tenant

from django.contrib.auth import BACKEND_SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.auth0_admin import (
    AUTH0_BACKEND_PATH,
    INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME,
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
        request.user = AnonymousUser()

        with patch("accounts.auth0_admin.admin.site.login") as mock_admin_login:
            mock_admin_login.return_value = HttpResponse("django_admin_response")
            result = admin_login_entrypoint(request)

            mock_admin_login.assert_called_once_with(request)
            assert result.content == b"django_admin_response"

    def test_require_idp_false_authenticated_staff_honors_next_param(
        self, request_factory, mock_tenant_settings_require_idp_false, admin_user_with_auth0_id
    ):
        """For non-Auth0 sites, an already-authenticated staff user hitting /admin/login/?next=...
        must be redirected to next with EFB cookie set, not to /admin/ (which is what Django's
        default admin login does for authenticated users, ignoring next)."""
        request = request_factory.get("/admin/login/?next=/admin/form-builder/")
        request.user = admin_user_with_auth0_id

        with patch("accounts.auth0_admin.set_efb_token_cookie") as mock_set_cookie:
            result = admin_login_entrypoint(request)

            assert result.status_code == 302
            assert result.url == "/admin/form-builder/"
            mock_set_cookie.assert_called_once_with(request, result)

    def test_require_idp_true_redirects_to_auth0(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that when require_idp=True, user is redirected to Auth0 login."""
        request = request_factory.get("/admin/login/?next=/admin/some/page")
        request.user = AnonymousUser()

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(result.url).query)
        assert parsed.get("next", [""])[0] == "/admin/some/page"
        assert parsed.get("org_id", [""])[0] == "org_test123"

    def test_preserves_next_parameter(self, request_factory, mock_tenant_settings_require_idp_true):
        """Test that the next parameter is properly preserved in Auth0 flow."""
        request = request_factory.get("/admin/login/?next=/admin/custom/path")
        request.user = AnonymousUser()

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(result.url).query)
        assert parsed.get("next", [""])[0] == "/admin/custom/path"
        assert parsed.get("org_id", [""])[0] == "org_test123"

    def test_require_idp_true_no_org_id_redirects_to_auth0_without_org_id(
        self, request_factory, mock_tenant_settings_require_idp_true_no_org
    ):
        """Common-DB sites (require_idp=True, no idp_org_id) route to the Auth0 initiator
        without an organization parameter, rather than falling back to Django admin."""
        request = request_factory.get("/admin/login/?next=/admin/some/page")
        request.user = AnonymousUser()

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME) in result.url
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(result.url).query)
        assert parsed.get("next", [""])[0] == "/admin/some/page"
        assert "org_id" not in parsed

    def test_handles_tenant_settings_error(self, request_factory):
        """Test that tenant settings errors fall back to Django admin login."""
        request = request_factory.get("/admin/login/")
        request.user = AnonymousUser()

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
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(result.url).query)
        assert parsed.get("next", [""])[0] == "/admin/"
        assert parsed.get("org_id", [""])[0] == "org_test123"

    def test_authenticated_staff_user_skips_auth0_and_sets_efb_cookie(
        self, request_factory, mock_tenant_settings_require_idp_true, admin_user_with_auth0_id
    ):
        """When require_idp=True and user authenticated via Auth0, skip Auth0 and set EFB cookie."""
        request = request_factory.get("/admin/login/?next=/admin/form-builder/")
        request.user = admin_user_with_auth0_id
        request.session = {BACKEND_SESSION_KEY: AUTH0_BACKEND_PATH}

        with patch("accounts.auth0_admin.set_efb_token_cookie") as mock_set_cookie:
            result = admin_login_entrypoint(request)

            assert result.status_code == 302
            assert result.url == "/admin/form-builder/"
            mock_set_cookie.assert_called_once_with(request, result)

    def test_authenticated_staff_user_non_auth0_session_redirects_to_auth0(
        self, request_factory, mock_tenant_settings_require_idp_true, admin_user_with_auth0_id
    ):
        """When require_idp=True and user has a Django session from a non-Auth0 backend,
        they must be forced through Auth0 rather than bypassing it."""
        request = request_factory.get("/admin/login/?next=/admin/form-builder/")
        request.user = admin_user_with_auth0_id
        request.session = {BACKEND_SESSION_KEY: "django.contrib.auth.backends.ModelBackend"}

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME) in result.url
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(result.url).query)
        assert parsed.get("next", [""])[0] == "/admin/form-builder/"

    def test_authenticated_staff_user_default_next(
        self, request_factory, mock_tenant_settings_require_idp_true, admin_user_with_auth0_id
    ):
        """When no next parameter, authenticated user redirects to /admin/."""
        request = request_factory.get("/admin/login/")
        request.user = admin_user_with_auth0_id
        request.session = {BACKEND_SESSION_KEY: AUTH0_BACKEND_PATH}

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
        assert reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME) in result.url

    def test_unauthenticated_user_redirects_to_auth0(self, request_factory, mock_tenant_settings_require_idp_true):
        """When require_idp=True and user is not authenticated, redirect to Auth0."""
        request = request_factory.get("/admin/login/?next=/admin/form-builder/")
        request.user = AnonymousUser()

        result = admin_login_entrypoint(request)

        assert result.status_code == 302
        assert reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME) in result.url
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(result.url).query)
        assert parsed.get("next", [""])[0] == "/admin/form-builder/"


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

    def test_missing_org_id_omits_organization_parameter(self, request_factory):
        """Common-DB sites (no org_id) must omit the organization parameter entirely,
        rather than passing organization=None, so Auth0 uses the tenant's Default Directory."""
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
            # organization must not be passed at all when org_id is missing
            assert "organization" not in call_args[1]

    @pytest.mark.parametrize("query_string", ["?org_id=org_test123", ""], ids=["org_scoped", "common_db"])
    def test_forces_login_prompt_to_prevent_silent_sso_reuse(self, request_factory, query_string):
        """The initiator must send prompt=login on every admin login — org-scoped and common-DB
        alike — so a retry re-prompts at Auth0 instead of silently reusing an existing SSO
        session. Without it, a rejected non-admin identity is re-asserted on every retry and the
        user is stuck in a login loop."""
        request = request_factory.get(f"/auth/admin-login/{query_string}")
        request.session = {}
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            _ = initiate_auth0_admin_login(request)

            call_kwargs = mock_redirect.call_args[1]
            assert call_kwargs["prompt"] == "login"
            # prompt=login must ride alongside the organization param, not displace it:
            # a future rewrite of extra_params must not drop org while keeping the prompt.
            if query_string:
                assert call_kwargs["organization"] == "org_test123"
            else:
                assert "organization" not in call_kwargs


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAuth0Callback:
    """Test the auth0_callback function."""

    def test_successful_authentication_and_redirect(self, request_factory, admin_user_with_auth0_id):
        """Active, linked staff user: the inline tenant-scoped lookup resolves the real user,
        logs them in, sets the EFB cookie, and redirects to the session's next target."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/target"}

        mock_token = Mock()
        # token.get("userinfo") returns this dict; .get("sub") matches the fixture's auth0_id.
        mock_token.get.return_value = {"sub": "auth0|123456789", "email": "admin@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin.login") as mock_login:
                with patch("accounts.auth0_admin.set_efb_token_cookie") as mock_set_efb_cookie:

                    mock_token_exchange.return_value = mock_token

                    result = auth0_callback(request)

                    mock_token_exchange.assert_called_once_with(request)

                    mock_login.assert_called_once_with(request, admin_user_with_auth0_id, backend=AUTH0_BACKEND_PATH)

                    mock_set_efb_cookie.assert_called_once_with(request, result)

                    assert result.status_code == 302
                    assert result.url == "/admin/target"

                    assert "auth0_admin_next" not in request.session

    def test_common_db_user_without_org_id_claim_authenticates(self, request_factory, admin_user_with_auth0_id):
        """Common-DB tokens carry no org_id claim. The callback keys only on the sub claim
        (since ERA-13339) and must still authenticate the user. Only the token exchange is
        mocked here, so the callback's inline tenant-scoped auth0_id lookup runs for real."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/target"}

        common_db_token = Mock()
        # No org_id claim in userinfo - this is what distinguishes a common-DB token.
        common_db_token.get.return_value = {"sub": "auth0|123456789", "email": "admin@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin.login") as mock_login:
                with patch("accounts.auth0_admin.set_efb_token_cookie"):

                    mock_token_exchange.return_value = common_db_token

                    result = auth0_callback(request)

                    mock_login.assert_called_once_with(request, admin_user_with_auth0_id, backend=AUTH0_BACKEND_PATH)
                    assert result.status_code == 302
                    assert result.url == "/admin/target"

    def test_does_not_exist_redirects_to_link_accounts(self, request_factory):
        """No active user matches the sub for this tenant: the callback redirects to the
        in-product account-linking on-ramp (302), not a 403."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        mock_token = Mock()
        # A sub with no corresponding user in this tenant.
        mock_token.get.return_value = {"sub": "auth0|no-such-user", "email": "nobody@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            mock_token_exchange.return_value = mock_token

            result = auth0_callback(request)

            assert result.status_code == 302
            assert result.url == reverse("link_accounts")

    def test_inactive_linked_user_redirects_to_link_accounts(self, request_factory):
        """An inactive user linked to the sub is filtered out by is_active=True, hitting the
        DoesNotExist path: the callback redirects to the account-linking on-ramp (302)."""
        User.objects.create_user(
            username="inactiveadmin",
            email="inactive@example.com",
            is_staff=True,
            is_active=False,
            auth0_id="auth0|inactive123",
        )
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        mock_token = Mock()
        mock_token.get.return_value = {"sub": "auth0|inactive123", "email": "inactive@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            mock_token_exchange.return_value = mock_token

            result = auth0_callback(request)

            assert result.status_code == 302
            assert result.url == reverse("link_accounts")

    def test_non_staff_user_returns_403_without_redirect(self, request_factory):
        """An active, linked, non-staff user is resolved but rejected with 403. It must NOT
        redirect to the link page (which rejects already-linked users -> dead-end)."""
        User.objects.create_user(
            username="regularlinked",
            email="regular@example.com",
            is_staff=False,
            is_active=True,
            auth0_id="auth0|nonstaff123",
        )
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        mock_token = Mock()
        mock_token.get.return_value = {"sub": "auth0|nonstaff123", "email": "regular@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            mock_token_exchange.return_value = mock_token

            result = auth0_callback(request)

            assert result.status_code == 403
            assert b"Authentication failed - insufficient privileges" in result.content

    def test_multiple_objects_returned_returns_403(self, request_factory):
        """Defensive path: if the lookup raises MultipleObjectsReturned, the callback returns
        403 rather than crashing into a 500 or leaking which users matched."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        mock_token = Mock()
        mock_token.get.return_value = {"sub": "auth0|ambiguous", "email": "ambiguous@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin.User.objects.get", side_effect=User.MultipleObjectsReturned):
                mock_token_exchange.return_value = mock_token

                result = auth0_callback(request)

                assert result.status_code == 403
                assert b"Authentication failed" in result.content

    def test_missing_sub_claim_returns_400(self, request_factory):
        """A token whose userinfo lacks the sub claim returns 400 before any user lookup."""
        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}

        mock_token = Mock()
        # token.get("userinfo") returns {}, so .get("sub") is None.
        mock_token.get.return_value = {}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            mock_token_exchange.return_value = mock_token

            result = auth0_callback(request)

            assert result.status_code == 400
            assert b"Authentication error" in result.content

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
        request.user = admin_user_with_auth0_id

        mock_token = Mock()
        mock_token.get.return_value = {"sub": "auth0|123456789", "email": "admin@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            with patch("accounts.auth0_admin.login"):
                with patch("accounts.auth0_admin.set_efb_token_cookie"):

                    mock_token_exchange.return_value = mock_token

                    result = auth0_callback(request)

                    assert result.status_code == 302
                    assert result.url == "/admin/"

    def test_cross_tenant_active_staff_user_redirects_to_link_accounts(self, request_factory, five_tenants, das_tenant):
        """An active staff user holding this auth0_id in a DIFFERENT tenant must not satisfy
        the callback: the tenant-scoped lookup finds no match in the active tenant, so the
        callback redirects to the link-accounts on-ramp (302) rather than logging anyone in.
        Proves the admin callback's auth0_id lookup is tenant-isolated."""
        foreign_sub = "auth0|cross-tenant-admin"
        User.objects.create_user(
            username="foreign_tenant_admin",
            email="foreign-admin@example.com",
            is_staff=True,
            is_active=True,
            auth0_id=foreign_sub,
            das_tenant=five_tenants[0],
        )
        # five_tenants resets the active tenant to None at setup; re-pin to das_tenant so the
        # callback's lookup runs scoped to the active tenant (mirrors the gate's
        # test_user_lookup_is_tenant_scoped and the test_permissionsets.py idiom).
        set_current_tenant(das_tenant)

        request = request_factory.get("/auth/callback/")
        request.session = {"auth0_admin_next": "/admin/"}
        mock_token = Mock()
        mock_token.get.return_value = {"sub": foreign_sub, "email": "foreign-admin@example.com"}

        with patch("accounts.auth0_admin._admin_auth0_client.auth0.authorize_access_token") as mock_token_exchange:
            mock_token_exchange.return_value = mock_token
            result = auth0_callback(request)

        assert result.status_code == 302
        assert result.url == reverse("link_accounts")


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
