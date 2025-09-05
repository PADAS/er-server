"""
Test that OAuth2 tokens take priority over session cookies in authentication.
"""

import pytest
from oauth2_provider.models import get_access_token_model

from django.test import RequestFactory

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

    def test_no_authentication_when_invalid_token(self, user):
        """Test that invalid OAuth2 token doesn't prevent session authentication."""
        # Create request with invalid OAuth2 token
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer invalid_token_12345"

        # Set session user
        request.user = user

        # Test authentication
        auth = PriorityOAuth2SessionAuthentication()
        result = auth.authenticate(request)

        # Should fall back to session authentication
        assert result is not None
        assert result[0] == user

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
