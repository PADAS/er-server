"""
Tests for Auth0JWTAuthentication backend.
"""

from __future__ import annotations

import logging
import time
from typing import Final
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

OIDC_PAPE_MFA_URI: Final = "http://schemas.openid.net/pape/policies/2007/06/multi-factor"
ACR_CLAIM: Final = "https://pamdas.org/acr"
MFA_TIME_CLAIM: Final = "https://pamdas.org/mfa_time"


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
        mock.feature_flags.require_mfa = False
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

    def test_no_token_in_header_or_query_params_returns_anonymous_user(self):
        """When require_idp=True but no token in header or query params, return AnonymousUser."""
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

    def test_bypass_auth0_application_skips_jwt_and_allows_fallback(self, mock_tenant_settings, user, application):
        """
        When require_idp=True, we usually fail closed to prevent legacy OAuth2 use.
        This test verifies the explicit carve-out: if the incoming Bearer token matches
        a DOT access token and its OAuth2 application has bypass_auth0=True, we
        return None to allow DRF to continue to OAuth2 authentication.
        """
        assert application.bypass_auth0 is True

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

    def test_non_bypass_auth0_application_fails_closed(self, mock_tenant_settings, user, application):
        """
        If the incoming Bearer token is a DOT access token whose application has
        bypass_auth0=False, authenticate() fails closed with AuthenticationFailed
        rather than allowing fallback to OAuth2 or falling through to JWT validation.
        """
        application.bypass_auth0 = False
        application.save()

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(request)

    def test_dot_token_with_null_application_proceeds_to_jwt_validation(self, mock_tenant_settings, user, application):
        """
        A DOT access token whose application FK is null is not recognized as a
        legacy OAuth2 token. It falls through to Auth0 JWT validation, which
        rejects the opaque string.
        """
        access_token = AccessTokenFactory(user=user, application=application)
        access_token.application = None
        access_token.save()

        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        with patch(
            "accounts.backends.ResourceProtector.validate_request",
            side_effect=Exception("Invalid token"),
        ) as mock_validate:
            with pytest.raises(AuthenticationFailed):
                Auth0JWTAuthentication().authenticate(request)

        assert mock_validate.call_count == 1

    def test_duplicate_dot_tokens_propagate_as_server_error(self, mock_tenant_settings, user, application):
        """
        If multiple access tokens share the same token value (a constraint
        violation), the lookup raises MultipleObjectsReturned rather than
        silently picking one — surfacing the data integrity issue as a 500.
        """
        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        mock_qs = MagicMock()
        mock_qs.get.side_effect = AccessToken.MultipleObjectsReturned

        with patch("accounts.backends.AccessToken.objects") as mock_objects:
            mock_objects.select_related.return_value = mock_qs
            with pytest.raises(AccessToken.MultipleObjectsReturned):
                Auth0JWTAuthentication().authenticate(request)

    def test_bypass_auth0_true_logs_debug(self, mock_tenant_settings, user, application, caplog):
        """When a DOT token's application has bypass_auth0=True, a DEBUG message is logged."""
        assert application.bypass_auth0 is True

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        with caplog.at_level(logging.DEBUG, logger="django.request"):
            with patch(
                "accounts.backends.ResourceProtector.validate_request",
                side_effect=Exception("should not be called"),
            ):
                Auth0JWTAuthentication().authenticate(request)

        assert any("bypass_auth0=True" in message and application.client_id in message for message in caplog.messages)

    def test_bypass_auth0_false_logs_warning(self, mock_tenant_settings, user, application, caplog):
        """When a DOT token's application has bypass_auth0=False, a WARNING message is logged."""
        application.bypass_auth0 = False
        application.save()

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        with caplog.at_level(logging.WARNING, logger="django.request"):
            with pytest.raises(AuthenticationFailed):
                Auth0JWTAuthentication().authenticate(request)

        assert any("bypass_auth0=False" in message and application.client_id in message for message in caplog.messages)

    def test_query_param_token_with_bypass_auth0_allows_fallback(self, mock_tenant_settings, user, application):
        """
        When require_idp=True and a DOT token is provided via ?auth= query param
        (no Authorization header), the bypass_auth0 gate applies and returns None
        to allow the DRF auth chain to continue to BearerTokenInUrlAuthentication.
        """
        assert application.bypass_auth0 is True

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get(f"/api/test/?auth={access_token.token}")

        with patch(
            "accounts.backends.ResourceProtector.validate_request",
            side_effect=Exception("should not be called"),
        ):
            result = Auth0JWTAuthentication().authenticate(request)

        assert result is None

    def test_query_param_token_without_bypass_auth0_fails_closed(self, mock_tenant_settings, user, application):
        """
        When require_idp=True and a DOT token is provided via ?auth= but the
        application has bypass_auth0=False, authenticate() fails closed.
        """
        application.bypass_auth0 = False
        application.save()

        access_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get(f"/api/test/?auth={access_token.token}")

        with pytest.raises(AuthenticationFailed):
            Auth0JWTAuthentication().authenticate(request)

    def test_header_takes_precedence_over_query_param(self, mock_tenant_settings, user, application):
        """
        When both Authorization header and ?auth= are present, the header
        token is used. Verified by giving the header token bypass_auth0=True
        and the query param a non-DOT value — if the query param were chosen,
        it would fall through to JWT validation and fail.
        """
        assert application.bypass_auth0 is True

        header_token = AccessTokenFactory(user=user, application=application)
        factory = RequestFactory()
        request = factory.get(
            "/api/test/?auth=query-param-value-should-be-ignored",
            HTTP_AUTHORIZATION=f"Bearer {header_token.token}",
        )

        with patch(
            "accounts.backends.ResourceProtector.validate_request",
            side_effect=Exception("should not be called"),
        ):
            result = Auth0JWTAuthentication().authenticate(request)

        assert result is None

    @pytest.mark.parametrize(
        "query_string",
        [
            pytest.param("?auth=", id="empty_auth_value"),
            pytest.param("?auth", id="auth_key_no_value"),
        ],
    )
    def test_empty_query_param_token_returns_anonymous(self, mock_tenant_settings, query_string):
        """An empty or valueless ?auth= query param is treated as no token at all."""
        factory = RequestFactory()
        request = factory.get(f"/api/test/{query_string}")

        result = Auth0JWTAuthentication().authenticate(request)

        assert isinstance(result[0], AnonymousUser)
        assert result[1] is None

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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAuth0MfaStepUp:
    """MFA gating (acr / mfa_time) and RFC 9470 step-up emission on require_mfa sites."""

    MFA_MAX_AGE_SECONDS = 3600

    @pytest.fixture(autouse=True)
    def require_mfa_enabled(self, mock_tenant_settings):
        """Turn on per-site MFA for this class; individual tests may override."""
        mock_tenant_settings.feature_flags.require_mfa = True
        mock_tenant_settings.feature_flags.mfa_max_age_seconds = self.MFA_MAX_AGE_SECONDS
        return mock_tenant_settings

    @pytest.fixture
    def set_claims(self, mock_auth0_validator, mock_relevant_token_claims):
        """Set the claims the validated JWT will carry (adds to the default sub)."""

        def _set(**claim_overrides):
            mock_auth0_validator.authenticate_token.return_value = mock_relevant_token_claims(**claim_overrides)

        return _set

    @staticmethod
    def _expected_challenge(max_age_seconds):
        return (
            'Bearer error="insufficient_user_authentication", '
            f'acr_values="{OIDC_PAPE_MFA_URI}", max_age="{max_age_seconds}"'
        )

    @staticmethod
    def _authenticate_expecting_step_up(request):
        authenticator = Auth0JWTAuthentication()
        with pytest.raises(AuthenticationFailed):
            authenticator.authenticate(request)
        return authenticator.authenticate_header(request)

    def test_missing_acr_claim_emits_step_up_challenge(self, api_request_for_test, mock_auth0_validator):
        """A token with no acr claim on a require_mfa site gets the step-up 401."""
        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(self.MFA_MAX_AGE_SECONDS)

    def test_acr_not_multi_factor_emits_step_up_challenge(self, api_request_for_test, set_claims):
        """An acr that is not the OIDC PAPE multi-factor URI gets the step-up 401."""
        set_claims(**{ACR_CLAIM: "urn:example:weak", MFA_TIME_CLAIM: int(time.time())})

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(self.MFA_MAX_AGE_SECONDS)

    def test_missing_mfa_time_emits_step_up_challenge(self, api_request_for_test, set_claims):
        """A valid acr but no mfa_time claim gets the step-up 401."""
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI})

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(self.MFA_MAX_AGE_SECONDS)

    def test_stale_mfa_time_emits_step_up_challenge(self, api_request_for_test, set_claims):
        """An mfa_time older than the configured window gets the step-up 401."""
        stale = int(time.time()) - (self.MFA_MAX_AGE_SECONDS + 3600)
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI, MFA_TIME_CLAIM: stale})

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(self.MFA_MAX_AGE_SECONDS)

    def test_non_numeric_mfa_time_emits_step_up_challenge(self, api_request_for_test, set_claims):
        """A non-numeric mfa_time is treated as invalid and gets the step-up 401."""
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI, MFA_TIME_CLAIM: "not-a-timestamp"})

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(self.MFA_MAX_AGE_SECONDS)

    def test_mfa_time_just_past_clock_skew_emits_step_up_challenge(self, api_request_for_test, set_claims):
        """120s beyond the window exceeds the 60s clock-skew tolerance and gets the step-up 401."""
        too_old = int(time.time()) - (self.MFA_MAX_AGE_SECONDS + 120)
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI, MFA_TIME_CLAIM: too_old})

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(self.MFA_MAX_AGE_SECONDS)

    def test_step_up_max_age_reflects_configured_window(
        self, api_request_for_test, mock_auth0_validator, mock_tenant_settings
    ):
        """The challenge's max_age echoes the site's configured mfa_max_age_seconds."""
        mock_tenant_settings.feature_flags.mfa_max_age_seconds = 1800

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(1800)

    def test_missing_mfa_max_age_falls_back_to_one_year(
        self, api_request_for_test, mock_auth0_validator, mock_tenant_settings
    ):
        """When the site has no mfa_max_age_seconds configured, the challenge uses the 1-year default."""
        mock_tenant_settings.feature_flags.mfa_max_age_seconds = None

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(31_536_000)

    def test_zero_mfa_max_age_is_honored_not_treated_as_unset(
        self, api_request_for_test, set_claims, mock_tenant_settings
    ):
        """A configured mfa_max_age_seconds of 0 is honored (strict), not defaulted to the 1-year window.

        Only an unset (None) value falls back to the default; 0 means "MFA must be within the
        clock-skew window", so a token whose MFA is 120s old must get the step-up 401.
        """
        mock_tenant_settings.feature_flags.mfa_max_age_seconds = 0
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI, MFA_TIME_CLAIM: int(time.time()) - 120})

        header = self._authenticate_expecting_step_up(api_request_for_test)

        assert header == self._expected_challenge(0)

    def test_fresh_mfa_authenticates_successfully(
        self, api_request_for_test, das_user_with_auth0_id_for_test, set_claims
    ):
        """A valid acr with a recent mfa_time passes the gate and returns the user."""
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI, MFA_TIME_CLAIM: int(time.time()) - 60})

        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result == (das_user_with_auth0_id_for_test, None)

    def test_mfa_time_within_clock_skew_authenticates(
        self, api_request_for_test, das_user_with_auth0_id_for_test, set_claims
    ):
        """An mfa_time within the 60s clock-skew tolerance past the window still passes."""
        within_skew = int(time.time()) - (self.MFA_MAX_AGE_SECONDS + 30)
        set_claims(**{ACR_CLAIM: OIDC_PAPE_MFA_URI, MFA_TIME_CLAIM: within_skew})

        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result == (das_user_with_auth0_id_for_test, None)

    def test_require_mfa_false_skips_mfa_gate(
        self, api_request_for_test, das_user_with_auth0_id_for_test, mock_auth0_validator, mock_tenant_settings
    ):
        """With require_mfa False, a token lacking acr/mfa_time still authenticates."""
        mock_tenant_settings.feature_flags.require_mfa = False

        result = Auth0JWTAuthentication().authenticate(api_request_for_test)

        assert result == (das_user_with_auth0_id_for_test, None)

    def test_non_mfa_failure_keeps_plain_bearer_header(self, api_request_for_test):
        """A non-MFA auth failure (invalid token) keeps the plain Bearer challenge, not the step-up."""
        authenticator = Auth0JWTAuthentication()
        with patch("accounts.backends.ResourceProtector.validate_request", side_effect=Exception("bad token")):
            with pytest.raises(AuthenticationFailed):
                authenticator.authenticate(api_request_for_test)

        assert authenticator.authenticate_header(api_request_for_test) == "Bearer"

    def test_bypass_auth0_dot_token_skips_mfa_gate(self, user, application):
        """A legacy bypass_auth0 DOT token returns None before the MFA gate is reached."""
        access_token = AccessTokenFactory(user=user, application=application)
        request = RequestFactory().get("/api/test/", HTTP_AUTHORIZATION=f"Bearer {access_token.token}")

        with patch(
            "accounts.backends.ResourceProtector.validate_request",
            side_effect=Exception("should not be called"),
        ):
            result = Auth0JWTAuthentication().authenticate(request)

        assert result is None
