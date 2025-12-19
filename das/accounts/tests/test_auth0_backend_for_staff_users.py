"""
Tests for Auth0BackendForStaffUsers authentication backend.
"""

from unittest.mock import Mock

import pytest

from django.test import RequestFactory

from accounts.backends import Auth0BackendForStaffUsers


@pytest.fixture
def auth0_backend():
    """Create an instance of Auth0BackendForStaffUsers backend."""
    return Auth0BackendForStaffUsers()


@pytest.fixture
def mock_request():
    """Create a mock Django request."""
    factory = RequestFactory()
    return factory.get("/admin/")


@pytest.fixture
def mock_oauth2_token():
    """Create a mock OAuth2Token with userinfo."""
    token = Mock()
    token.get.return_value = {"sub": "auth0|123456789", "email": "staff@example.com", "name": "Staff User"}
    return token


@pytest.fixture
def das_staff_user_with_auth0_id(user):
    """Create a DAS staff user with auth0_id set."""
    user.auth0_id = "auth0|123456789"
    user.is_staff = True
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def das_non_staff_user_with_auth0_id(user):
    """Create a DAS non-staff user with auth0_id set."""
    user.auth0_id = "auth0|123456789"
    user.is_staff = False
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def das_inactive_staff_user_with_auth0_id(user):
    """Create an inactive DAS staff user with auth0_id set."""
    user.auth0_id = "auth0|123456789"
    user.is_staff = True
    user.is_active = False
    user.save()
    return user


@pytest.mark.django_db
class TestAuth0BackendForStaffUsersAuthenticate:
    """Test the authenticate method of Auth0BackendForStaffUsers."""

    def test_successful_authentication_with_staff_user(
        self, auth0_backend, mock_request, mock_oauth2_token, das_staff_user_with_auth0_id
    ):
        """Test successful authentication with a staff user."""
        result = auth0_backend.authenticate(mock_request, token=mock_oauth2_token)

        assert result == das_staff_user_with_auth0_id
        assert result.is_staff is True
        assert result.is_active is True

    def test_authentication_fails_with_non_staff_user(
        self, auth0_backend, mock_request, mock_oauth2_token, das_non_staff_user_with_auth0_id
    ):
        """Test authentication fails when user is not staff."""
        result = auth0_backend.authenticate(mock_request, token=mock_oauth2_token)

        assert result is None

    def test_authentication_fails_with_inactive_user(
        self, auth0_backend, mock_request, mock_oauth2_token, das_inactive_staff_user_with_auth0_id
    ):
        """Test authentication fails when user is inactive."""
        result = auth0_backend.authenticate(mock_request, token=mock_oauth2_token)

        assert result is None

    def test_authentication_fails_user_does_not_exist(self, auth0_backend, mock_request, mock_oauth2_token):
        """Test authentication fails when user with auth0_id doesn't exist."""
        result = auth0_backend.authenticate(mock_request, token=mock_oauth2_token)

        assert result is None

    def test_authentication_with_no_token(self, auth0_backend, mock_request):
        """Test authentication with no token provided."""
        result = auth0_backend.authenticate(mock_request, token=None)

        assert result is None


@pytest.mark.django_db
class TestAuth0BackendForStaffUsersGetUser:
    """Test the get_user method of Auth0BackendForStaffUsers."""

    def test_get_user_success(self, auth0_backend, das_staff_user_with_auth0_id):
        """Test successful user retrieval by ID."""
        result = auth0_backend.get_user(das_staff_user_with_auth0_id.id)

        assert result == das_staff_user_with_auth0_id

    def test_get_user_fails_with_non_staff_user(self, auth0_backend, das_non_staff_user_with_auth0_id):
        """Test get_user fails when user is not staff."""
        result = auth0_backend.get_user(das_non_staff_user_with_auth0_id.id)

        assert result is None

    def test_get_user_fails_with_inactive_user(self, auth0_backend, das_inactive_staff_user_with_auth0_id):
        """Test get_user fails when user is inactive."""
        result = auth0_backend.get_user(das_inactive_staff_user_with_auth0_id.id)

        assert result is None

    def test_get_user_does_not_exist(self, auth0_backend):
        """Test get_user when user ID doesn't exist."""
        from uuid import uuid4

        non_existent_id = uuid4()

        result = auth0_backend.get_user(non_existent_id)

        assert result is None

    def test_get_user_with_none_id(self, auth0_backend):
        """Test get_user with None as user ID."""
        result = auth0_backend.get_user(None)

        assert result is None
