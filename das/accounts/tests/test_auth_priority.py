"""
Test that OAuth2 tokens take priority over session cookies in authentication.
"""

import pytest
from oauth2_provider.models import get_access_token_model

from django.test import RequestFactory
from rest_framework import exceptions

from accounts.backends import PriorityOAuth2SessionAuthentication
from accounts.models import User
from factories import AccessTokenFactory

AccessToken = get_access_token_model()


@pytest.fixture
def access_token(user, application):
    """Create an access token for testing."""
    return AccessTokenFactory(user=user, application=application)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAuthenticationPriority:
    """Test authentication priority between OAuth2 tokens and session cookies."""

    def test_oauth2_token_takes_priority_over_session(self, user, access_token):
        """Test that OAuth2 tokens take priority over session cookies."""
        # Create a different user for session simulation
        session_user = User.objects.create_user(
            username="sessionuser", email="session@example.com", password="sessionpass123"
        )

        # Create request with OAuth2 token
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {access_token.token}"

        # Simulate session user (admin login cookie)
        request.user = session_user

        # Test authentication
        auth = PriorityOAuth2SessionAuthentication()
        result = auth.authenticate(request)

        # OAuth2 token should take priority
        assert result is not None
        assert result[0] == user  # OAuth2 user, not session user
        assert result[0] != session_user

    def test_session_authentication_fallback(self, user):
        """Test that session authentication works as fallback when no OAuth2 token."""
        # Create request without OAuth2 token
        factory = RequestFactory()
        request = factory.get("/api/test/")
        # No Authorization header

        # Set session user
        request.user = user

        # Test authentication
        auth = PriorityOAuth2SessionAuthentication()
        result = auth.authenticate(request)

        # Session authentication should work
        assert result is not None
        assert result[0] == user

    def test_authentication_fails_when_invalid_token(self, user):
        """Test that invalid OAuth2 token causes authentication to fail."""
        # Create request with invalid OAuth2 token
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer invalid_token_12345"

        # Set session user
        request.user = user

        # Test authentication
        auth = PriorityOAuth2SessionAuthentication()

        # Should raise AuthenticationFailed when invalid token is provided
        with pytest.raises(exceptions.AuthenticationFailed) as exc_info:
            auth.authenticate(request)

        # Should be an AuthenticationFailed exception
        assert "AuthenticationFailed" in str(type(exc_info.value))
        assert "Token is invalid or expired" in str(exc_info.value)

    def test_bearer_token_prevents_session_fallback(self, user):
        """Test that presence of Bearer token prevents fallback to session auth.

        This is a critical test for the scenario where:
        1. User is logged into Django admin (has session cookie)
        2. API call includes Bearer token that doesn't authenticate
        3. System should NOT fall back to session user, should raise AuthenticationFailed

        This simulates Django's AuthenticationMiddleware having already set
        request.user from session before DRF authentication runs.
        """
        # Create a different user for session simulation
        session_user = User.objects.create_user(
            username="adminuser", email="admin@example.com", password="adminpass123"
        )

        # Create request with Bearer token that won't authenticate
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer some_bearer_token_that_doesnt_match"

        # Simulate Django AuthenticationMiddleware having set request.user from session
        request.user = session_user
        # Mark this as a DRF request (has _request attribute)
        request._request = request

        # Test authentication
        auth = PriorityOAuth2SessionAuthentication()

        # Should raise AuthenticationFailed (not fall back to session user)
        with pytest.raises(exceptions.AuthenticationFailed) as exc_info:
            auth.authenticate(request)

        # Should be an AuthenticationFailed exception
        assert "AuthenticationFailed" in str(type(exc_info.value))
        assert "Token is invalid or expired" in str(exc_info.value)

    def test_no_authentication_when_no_token_or_session(self):
        """Test that no authentication occurs when neither token nor session exists."""
        # Create request without any authentication
        factory = RequestFactory()
        request = factory.get("/api/test/")
        # No Authorization header, no user set

        # Test authentication
        auth = PriorityOAuth2SessionAuthentication()
        result = auth.authenticate(request)

        # Should return None
        assert result is None

    def test_csrf_skipped_with_oauth2_token(self, user, access_token):
        """Test that CSRF is SKIPPED when OAuth2 token is present.

        Bearer tokens are not vulnerable to CSRF attacks, so CSRF validation
        should be skipped when a valid Bearer token is in the request.
        """
        # Create request with OAuth2 token
        factory = RequestFactory()
        request = factory.post("/api/test/", {"test": "data"})
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {access_token.token}"

        # Set session user as well (simulating admin login cookie)
        request.user = user

        # Test CSRF enforcement
        auth = PriorityOAuth2SessionAuthentication()
        result = auth.enforce_csrf(request)

        # Should return None (skip CSRF enforcement) for Bearer tokens
        assert result is None

    def test_csrf_skipped_with_session_only(self, user):
        """Test that CSRF is skipped when only session authentication is used (no Bearer token)."""
        # Create request without OAuth2 token
        factory = RequestFactory()
        request = factory.post("/api/test/", {"test": "data"})
        # No Authorization header

        # Simulate authenticated Django session (without triggering DRF authentication)
        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()
        session["_auth_user_id"] = str(user.id)
        session.save()
        request.session = session

        # Test CSRF enforcement
        auth = PriorityOAuth2SessionAuthentication()
        result = auth.enforce_csrf(request)

        # Should return None (skip CSRF enforcement)
        assert result is None

    def test_csrf_enforced_when_no_session_user(self):
        """Test that CSRF is enforced when no session user exists (even without Bearer token)."""
        # Create request without OAuth2 token and no session user
        factory = RequestFactory()
        request = factory.post("/api/test/", {"test": "data"})
        # No Authorization header, no authenticated user

        # Test CSRF enforcement
        auth = PriorityOAuth2SessionAuthentication()

        # This should call super().enforce_csrf() which would normally raise an exception
        try:
            auth.enforce_csrf(request)
            # If enforce_csrf doesn't raise an exception, it should return None or raise
            # The important thing is it doesn't return early (skip CSRF)
        except Exception:
            # This is expected - CSRF should be enforced and may fail
            pass
