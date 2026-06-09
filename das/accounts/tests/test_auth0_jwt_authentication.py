"""
Tests for Auth0JWTAuthentication backend.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from oauth2_provider.models import get_access_token_model

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    PermissionDenied,
)

from accounts.backends import Auth0JWTAuthentication
from accounts.models import User
from factories import AccessTokenFactory

AccessToken = get_access_token_model()


@pytest.fixture
def das_user_with_auth0_id_for_test(user):
    """Create a DAS user with auth0_id set."""
    user.auth0_id = "auth0|123456789"
    user.save()
    return user


@pytest.fixture
def mock_relevant_token_claims(das_user_with_auth0_id_for_test):
    """Factory for creating JWT claims with configurable values."""

    def _create_claims(**overrides):
        default_claims = {
            "sub": das_user_with_auth0_id_for_test.auth0_id,
        }
        default_claims.update(overrides)
        return default_claims

    return _create_claims


@pytest.fixture
def mock_auth0_validator(mock_relevant_token_claims):
    """Mock the Auth0JWTBearerTokenValidator."""
    with patch("accounts.backends.Auth0JWTBearerTokenValidator") as mock_validator_class:
        mock_validator = MagicMock()
        mock_validator.TOKEN_TYPE = "bearer"
        mock_validator.authenticate_token.return_value = mock_relevant_token_claims()
        mock_validator_class.return_value = mock_validator
        yield mock_validator


@pytest.fixture(autouse=True)
def mock_tenant_settings():
    """Mock tenant settings with default feature flags."""
    with patch("accounts.backends.get_tenant_settings") as mock_settings:
        mock = Mock()
        mock.feature_flags.require_idp = True
        mock_settings.return_value = mock
        yield mock


@pytest.fixture
def api_request_for_test():
    """Create API request with Bearer token."""
    factory = RequestFactory()
    request = factory.get("/api/test/", HTTP_AUTHORIZATION="Bearer some-token")
    return request


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAuth0JWTAuthentication:
    """Test Auth0 JWT authentication backend."""

    def test_feature_flag_disabled_returns_none(self, mock_tenant_settings, api_request_for_test):
        """Test that authentication returns None when require_idp feature flag is disabled."""
        mock_tenant_settings.feature_flags.require_idp = False

        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result is None

    def test_tenant_resolution_failure_raises_api_exception(self, api_request_for_test):
        """Test that tenant resolution failure raises APIException (500)."""
        with patch("accounts.backends.get_tenant_settings", side_effect=Exception("Tenant lookup failed")):
            with pytest.raises(APIException):
                Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_jwt_validation_failure_raises_authentication_failed(self, mock_tenant_settings, api_request_for_test):
        """Test that JWT validation failure raises AuthenticationFailed."""
        with patch("accounts.backends.ResourceProtector.validate_request", side_effect=Exception("Invalid token")):
            with pytest.raises(AuthenticationFailed):
                Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_user_not_found_raises_authentication_failed(
        self, mock_tenant_settings, api_request_for_test, mock_auth0_validator, mock_relevant_token_claims
    ):
        """Test that user not found raises AuthenticationFailed."""
        mock_auth0_validator.authenticate_token.return_value = mock_relevant_token_claims(sub="auth0|nonexistent_user")

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_multiple_users_with_same_auth0_id_raises_authentication_failed(
        self, mock_tenant_settings, api_request_for_test, mock_auth0_validator
    ):
        """Test that MultipleObjectsReturned raises AuthenticationFailed.

        Guards against a data integrity issue where multiple active users share the same
        auth0_id. Without this handling, the exception would bubble up as a 500 error.
        """
        with patch("accounts.backends.User.objects.get", side_effect=User.MultipleObjectsReturned):
            with pytest.raises(AuthenticationFailed):
                Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_inactive_user_raises_authentication_failed(
        self, mock_tenant_settings, api_request_for_test, mock_auth0_validator, das_user_with_auth0_id_for_test
    ):
        """Test that inactive user raises AuthenticationFailed."""
        das_user_with_auth0_id_for_test.is_active = False
        das_user_with_auth0_id_for_test.save()

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(api_request_for_test)

    @pytest.mark.parametrize(
        "org_id_override",
        [
            pytest.param("org_some_value", id="with_org_id"),
            pytest.param(None, id="without_org_id"),
        ],
    )
    def test_authenticates_regardless_of_org_id_claim(
        self,
        org_id_override,
        api_request_for_test,
        das_user_with_auth0_id_for_test,
        mock_auth0_validator,
        mock_relevant_token_claims,
    ):
        """Test that authentication succeeds whether or not the JWT carries an org_id claim."""
        if org_id_override is not None:
            mock_auth0_validator.authenticate_token.return_value = mock_relevant_token_claims(org_id=org_id_override)
        else:
            mock_auth0_validator.authenticate_token.return_value = mock_relevant_token_claims()

        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result is not None
        assert result[0] == das_user_with_auth0_id_for_test
        assert result[1] is None

    def test_no_authorization_header_returns_anonymous_user_when_idp_required(self):
        """Test that when require_idp=True but no Authorization header, should return AnonymousUser."""
        factory = RequestFactory()
        request_without_auth = factory.get("/api/test/")

        result = Auth0JWTAuthentication().authenticate(request_without_auth)

        assert result is not None
        assert isinstance(result[0], AnonymousUser)
        assert result[1] is None

    def test_successful_authentication_returns_user(
        self, api_request_for_test, das_user_with_auth0_id_for_test, mock_auth0_validator
    ):
        """Test successful authentication flow."""
        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result is not None
        assert result[0] == das_user_with_auth0_id_for_test
        assert result[1] is None

    def test_allowlisted_oauth2_client_skips_auth0_and_allows_fallback(
        self, mock_tenant_settings, settings, user, application
    ):
        """
        When require_idp=True, we usually fail closed to prevent legacy OAuth2 use.
        This test verifies the explicit carve-out: if the incoming Bearer token matches
        a DOT access token and its OAuth2 application's client_id is allowlisted, we
        return None to allow DRF to continue to OAuth2 authentication.
        """
        settings.IDP_OAUTH2_CLIENT_IDS_ALLOWLIST = [application.client_id]

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        # Ensure Auth0 JWT validation path is not invoked
        with patch(
            "accounts.backends.ResourceProtector.validate_request",
            side_effect=Exception("should not be called"),
        ):
            result = Auth0JWTAuthentication().authenticate(request)

        assert result is None

    def test_non_allowlisted_oauth2_token_fails_closed(self, mock_tenant_settings, settings, user, application):
        """
        If the incoming Bearer token is one of our stored DOT access tokens but the
        OAuth2 client_id is not allowlisted, we must fail closed and block fallback.
        """
        settings.IDP_OAUTH2_CLIENT_IDS_ALLOWLIST = []

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(request)

    @pytest.mark.parametrize(
        "missing_sub",
        [
            pytest.param(None, id="sub_is_none"),
            pytest.param("", id="sub_is_empty_string"),
        ],
    )
    def test_missing_sub_claim_raises_authentication_failed(
        self, missing_sub, api_request_for_test, mock_auth0_validator, mock_relevant_token_claims
    ):
        """Test that a JWT without a valid sub claim is rejected.

        With the org_id check removed, we must fail closed on missing sub to
        prevent User.objects.get(auth0_id=None) from matching an unlinked user.
        """
        mock_auth0_validator.authenticate_token.return_value = mock_relevant_token_claims(sub=missing_sub)

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_keyword_is_bearer(self, api_request_for_test, das_user_with_auth0_id_for_test, mock_auth0_validator):
        """Test that WWW-Authenticate keyword is Bearer per RFC 6750."""
        assert Auth0JWTAuthentication().keyword == "Bearer"

    def test_auth0_authentication_is_first_in_settings(self):
        """Test that Auth0JWTAuthentication is first in REST_FRAMEWORK authentication classes.

        This test exists to enforce a critical security requirement: Auth0JWTAuthentication
        MUST be the first authentication class in the DRF authentication chain.

        Why this ordering is essential:

        1. When require_idp=False: Auth0JWTAuthentication returns None, allowing the chain
           to continue to other authentication methods (OAuth2, session auth, etc.)

        2. When require_idp=True: Auth0JWTAuthentication either succeeds OR raises
           AuthenticationFailed, which stops the authentication chain entirely.

        This prevents security bypasses where users could authenticate with legacy OAuth2
        tokens or session cookies when a tenant has mandated Auth0-only authentication.

        If Auth0JWTAuthentication were placed later in the chain, other authentication
        methods could succeed first, defeating the purpose of the require_idp feature flag.

        This test prevents accidental reordering that would create a security vulnerability.
        """
        from django.conf import settings

        auth_classes = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
        assert auth_classes[0] == "accounts.backends.Auth0JWTAuthentication"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAuth0JWTAuthenticationActAs:
    """Test act_as (HTTP_USER_PROFILE) impersonation through Auth0JWTAuthentication."""

    @staticmethod
    def _make_request(profile_header: str | None = None) -> object:
        factory = RequestFactory()
        kwargs: dict[str, str] = {"HTTP_AUTHORIZATION": "Bearer some-token"}
        if profile_header is not None:
            kwargs["HTTP_USER_PROFILE"] = profile_header
        return factory.get("/api/test/", **kwargs)

    def test_returns_user_unchanged_when_no_profile_header(self, das_user_with_auth0_id_for_test, mock_auth0_validator):
        """No HTTP_USER_PROFILE header → no substitution, original user returned."""
        request = self._make_request()
        result = Auth0JWTAuthentication().authenticate(request)

        assert result == (das_user_with_auth0_id_for_test, None)

    def test_returns_original_user_when_profile_is_self(self, das_user_with_auth0_id_for_test, mock_auth0_validator):
        """HTTP_USER_PROFILE == own PK → no substitution, original user returned."""
        request = self._make_request(profile_header=str(das_user_with_auth0_id_for_test.pk))
        result = Auth0JWTAuthentication().authenticate(request)

        assert result == (das_user_with_auth0_id_for_test, None)

    def test_returns_profile_user_when_authorized(
        self, das_user_with_auth0_id_for_test, create_user, mock_auth0_validator
    ):
        """Happy path: profile_user in act_as_profiles and header set → profile_user returned."""
        profile_user = create_user()
        das_user_with_auth0_id_for_test.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))
        result = Auth0JWTAuthentication().authenticate(request)

        assert result == (profile_user, None)

    def test_raises_permission_denied_when_profile_not_in_act_as_profiles(
        self, das_user_with_auth0_id_for_test, create_user, mock_auth0_validator
    ):
        """Target NOT in act_as_profiles raises PermissionDenied."""
        profile_user = create_user()
        # intentionally NOT added to act_as_profiles
        request = self._make_request(profile_header=str(profile_user.pk))
        with pytest.raises(PermissionDenied):
            Auth0JWTAuthentication().authenticate(request)

    @pytest.mark.parametrize(
        "is_staff, is_superuser",
        [
            pytest.param(True, False, id="staff"),
            pytest.param(False, True, id="superuser"),
            pytest.param(True, True, id="staff_and_superuser"),
        ],
    )
    def test_raises_permission_denied_when_profile_is_privileged(
        self, is_staff, is_superuser, das_user_with_auth0_id_for_test, create_user, mock_auth0_validator
    ):
        """Privileged target (staff or superuser) in act_as_profiles raises PermissionDenied."""
        profile_user = create_user(is_staff=is_staff, is_superuser=is_superuser)
        das_user_with_auth0_id_for_test.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))
        with pytest.raises(PermissionDenied):
            Auth0JWTAuthentication().authenticate(request)
