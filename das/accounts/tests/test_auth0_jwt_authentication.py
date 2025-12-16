"""
Tests for Auth0JWTAuthentication backend.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from django.test import RequestFactory
from rest_framework.exceptions import APIException, AuthenticationFailed

from accounts.backends import Auth0JWTAuthentication


@pytest.fixture
def das_user_with_auth0_id_for_test(user):
    """Create a DAS user with auth0_id set."""
    user.auth0_id = "auth0|123456789"
    user.save()
    return user


@pytest.fixture
def mock_relevant_token_claims(das_user_with_auth0_id_for_test, mock_tenant_settings):
    """Factory for creating JWT claims with configurable values."""

    def _create_claims(**overrides):
        default_claims = {
            "sub": das_user_with_auth0_id_for_test.auth0_id,
            "org_id": mock_tenant_settings.feature_flags.idp_org_id,
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
        mock.feature_flags.idp_org_id = "org_123456789"
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

    def test_inactive_user_raises_authentication_failed(
        self, mock_tenant_settings, api_request_for_test, mock_auth0_validator, das_user_with_auth0_id_for_test
    ):
        """Test that inactive user raises AuthenticationFailed."""
        das_user_with_auth0_id_for_test.is_active = False
        das_user_with_auth0_id_for_test.save()

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_org_id_mismatch_raises_authentication_failed(
        self, mock_tenant_settings, api_request_for_test, mock_auth0_validator, mock_relevant_token_claims
    ):
        """Test that organization ID mismatch raises AuthenticationFailed."""
        mock_auth0_validator.authenticate_token.return_value = mock_relevant_token_claims(org_id="org_different")

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(api_request_for_test)

    def test_successful_authentication_returns_user(
        self, api_request_for_test, das_user_with_auth0_id_for_test, mock_auth0_validator
    ):
        """Test successful authentication flow."""
        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result is not None
        assert result[0] == das_user_with_auth0_id_for_test
        assert result[1] is None

    def test_keyword_is_token(self, api_request_for_test, das_user_with_auth0_id_for_test, mock_auth0_validator):
        """Test that our keyword is Token."""
        assert Auth0JWTAuthentication().keyword == "Token"

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
