"""
Tests for NoLoginOAuth2Backend and NoLoginOAuth2Authentication in accounts/backends.py.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from accounts.backends import NoLoginOAuth2Authentication, NoLoginOAuth2Backend


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestNoLoginOAuth2Backend:

    @staticmethod
    def _make_request(profile_header: str | None = None) -> object:
        factory = RequestFactory()
        kwargs = {}
        if profile_header is not None:
            kwargs["HTTP_USER_PROFILE"] = profile_header
        return factory.get("/api/test/", **kwargs)

    @pytest.fixture(autouse=True)
    def mock_oauth2_backend_super(self, user) -> Generator[MagicMock]:
        """Patch OAuth2Backend.authenticate to return `user` by default and yield the mock."""
        with patch("oauth2_provider.backends.OAuth2Backend.authenticate", return_value=user) as mock_super:
            yield mock_super

    def test_returns_none_when_super_returns_none(self, mock_oauth2_backend_super):
        """If the super authenticate() returns None (auth failure), backend returns None."""
        mock_oauth2_backend_super.return_value = None
        request = self._make_request()
        result = NoLoginOAuth2Backend().authenticate(request)
        assert result is None

    def test_returns_none_when_user_is_nologin(self, user):
        """User with is_nologin=True is blocked even when super auth succeeds."""
        user.is_nologin = True
        user.save()
        request = self._make_request()
        result = NoLoginOAuth2Backend().authenticate(request)
        assert result is None

    def test_returns_user_when_request_is_none(self, user):
        """When request is None, act_as logic is skipped and the original user is returned."""
        result = NoLoginOAuth2Backend().authenticate(request=None)
        assert result is user

    def test_returns_user_unchanged_when_no_profile_header(self, user):
        """No HTTP_USER_PROFILE header means no substitution — same user returned."""
        request = self._make_request()
        result = NoLoginOAuth2Backend().authenticate(request)
        assert result is user

    def test_returns_anonymous_user_unchanged_when_profile_header_present(self, mock_oauth2_backend_super):
        """Anonymous user with HTTP_USER_PROFILE header skips impersonation and is returned as-is."""
        anon = AnonymousUser()
        anon.is_nologin = False
        mock_oauth2_backend_super.return_value = anon
        request = self._make_request(profile_header="00000000-0000-0000-0000-000000000001")
        result = NoLoginOAuth2Backend().authenticate(request)
        assert result is anon

    def test_returns_original_user_when_profile_is_self(self, user):
        """HTTP_USER_PROFILE == own PK → no substitution, original user returned."""
        request = self._make_request(profile_header=str(user.pk))
        result = NoLoginOAuth2Backend().authenticate(request)
        assert result is user

    def test_returns_profile_user_when_authorized(self, user, create_user):
        """Happy path: profile_user is in act_as_profiles, header set → profile_user returned."""
        profile_user = create_user()
        user.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))
        result = NoLoginOAuth2Backend().authenticate(request)
        assert result == profile_user

    def test_raises_permission_denied_when_profile_not_in_act_as_profiles(self, user, create_user):
        """Target user NOT in act_as_profiles raises PermissionDenied."""
        profile_user = create_user()
        # intentionally NOT added to act_as_profiles
        request = self._make_request(profile_header=str(profile_user.pk))
        with pytest.raises(PermissionDenied):
            NoLoginOAuth2Backend().authenticate(request)

    @pytest.mark.parametrize(
        "is_staff, is_superuser",
        [
            pytest.param(True, False, id="staff"),
            pytest.param(False, True, id="superuser"),
            pytest.param(True, True, id="staff_and_superuser"),
        ],
    )
    def test_raises_permission_denied_when_profile_is_privileged(self, is_staff, is_superuser, user, create_user):
        """Privileged target user (staff or superuser) in act_as_profiles raises PermissionDenied."""
        profile_user = create_user(is_staff=is_staff, is_superuser=is_superuser)
        user.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))
        with pytest.raises(PermissionDenied):
            NoLoginOAuth2Backend().authenticate(request)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestNoLoginOAuth2Authentication:

    @staticmethod
    def _make_request(profile_header: str | None = None) -> object:
        factory = RequestFactory()
        kwargs = {}
        if profile_header is not None:
            kwargs["HTTP_USER_PROFILE"] = profile_header
        return factory.get("/api/test/", **kwargs)

    @pytest.fixture(autouse=True)
    def mock_oauth2_auth_super(self, user) -> Generator[MagicMock]:
        """Patch OAuth2Authentication.authenticate to return (user, token) by default and yield the mock.

        The token used as the second element of the return value is accessible via mock.token.
        """
        token = MagicMock()
        with patch(
            "oauth2_provider.contrib.rest_framework.authentication.OAuth2Authentication.authenticate",
            return_value=(user, token),
        ) as mock_super:
            mock_super.token = token
            yield mock_super

    def test_returns_none_when_super_returns_none(self, mock_oauth2_auth_super):
        """If the super authenticate() returns None (auth failure), authentication returns None."""
        mock_oauth2_auth_super.return_value = None
        request = self._make_request()
        result = NoLoginOAuth2Authentication().authenticate(request)
        assert result is None

    def test_raises_authentication_failed_when_super_returns_none_with_oauth2_error(self, mock_oauth2_auth_super):
        """Super returns None with oauth2_error set on request → AuthenticationFailed raised."""
        mock_oauth2_auth_super.return_value = None
        request = self._make_request()
        request.oauth2_error = {"error": "invalid_token", "description": "Token has expired"}
        with pytest.raises(AuthenticationFailed):
            NoLoginOAuth2Authentication().authenticate(request)

    def test_raises_permission_denied_when_user_is_nologin(self, user):
        """User with is_nologin=True is blocked and PermissionDenied is raised."""
        user.is_nologin = True
        user.save()
        request = self._make_request()
        with pytest.raises(PermissionDenied):
            NoLoginOAuth2Authentication().authenticate(request)

    def test_returns_user_unchanged_when_no_profile_header(self, user, mock_oauth2_auth_super):
        """No HTTP_USER_PROFILE header → no substitution, original (user, token) tuple returned."""
        request = self._make_request()
        result = NoLoginOAuth2Authentication().authenticate(request)
        assert result == (user, mock_oauth2_auth_super.token)

    def test_returns_anonymous_user_unchanged_when_profile_header_present(self, mock_oauth2_auth_super):
        """Anonymous user with HTTP_USER_PROFILE header skips impersonation and is returned as-is."""
        anon = AnonymousUser()
        anon.is_nologin = False
        token = MagicMock()
        mock_oauth2_auth_super.return_value = (anon, token)
        request = self._make_request(profile_header="00000000-0000-0000-0000-000000000001")
        result = NoLoginOAuth2Authentication().authenticate(request)
        assert result == (anon, token)

    def test_returns_original_user_when_profile_is_self(self, user, mock_oauth2_auth_super):
        """HTTP_USER_PROFILE == own PK → no substitution, original user in tuple."""
        request = self._make_request(profile_header=str(user.pk))
        result = NoLoginOAuth2Authentication().authenticate(request)
        assert result == (user, mock_oauth2_auth_super.token)

    def test_returns_profile_user_when_authorized(self, user, create_user, mock_oauth2_auth_super):
        """Happy path: profile_user in act_as_profiles and header set → profile_user in tuple."""
        profile_user = create_user()
        user.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))
        result = NoLoginOAuth2Authentication().authenticate(request)
        assert result == (profile_user, mock_oauth2_auth_super.token)

    def test_raises_permission_denied_when_profile_not_in_act_as_profiles(self, user, create_user):
        """Target NOT in act_as_profiles raises PermissionDenied."""
        profile_user = create_user()
        request = self._make_request(profile_header=str(profile_user.pk))
        with pytest.raises(PermissionDenied):
            NoLoginOAuth2Authentication().authenticate(request)

    @pytest.mark.parametrize(
        "is_staff, is_superuser",
        [
            pytest.param(True, False, id="staff"),
            pytest.param(False, True, id="superuser"),
            pytest.param(True, True, id="staff_and_superuser"),
        ],
    )
    def test_raises_permission_denied_when_profile_is_privileged(self, is_staff, is_superuser, user, create_user):
        """Privileged target in act_as_profiles raises PermissionDenied."""
        profile_user = create_user(is_staff=is_staff, is_superuser=is_superuser)
        user.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))
        with pytest.raises(PermissionDenied):
            NoLoginOAuth2Authentication().authenticate(request)
