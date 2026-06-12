"""
Tests for the self-service Link Accounts page (ERA-13391).

Tests the form-based entry point that lets an existing ER user kick off the
PKCE Account Linker flow by supplying their legacy username/password.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client

from accounts.account_linker import SESSION_KEY_PREFIX
from accounts.link_accounts import (
    _ALREADY_LINKED_MESSAGE,
    _IDP_NOT_ENABLED_MESSAGE,
    _INVALID_CREDENTIALS_MESSAGE,
)

User = get_user_model()

_LINK_ACCOUNTS_URL = "/auth/link-accounts/"


def _mock_tenant_settings(*, require_idp: bool = True, idp_org_id: str = "") -> Mock:
    mock = Mock()
    mock.feature_flags.require_idp = require_idp
    mock.feature_flags.idp_org_id = idp_org_id
    mock.slug_name = "testsite"
    mock.domain = "testsite.pamdas.org"
    mock.url = "https://testsite.pamdas.org"
    return mock


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestLinkAccountsGet:
    @pytest.fixture(autouse=True)
    def _disable_ratelimit(self, settings):
        settings.RATELIMIT_ENABLE = False

    def test_renders_form_on_idp_enabled_tenant(self):
        client = Client()
        mock_ts = _mock_tenant_settings(require_idp=True, idp_org_id="")
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.link_accounts.get_tenant_settings", return_value=mock_ts):
                response = client.get(_LINK_ACCOUNTS_URL)
        assert response.status_code == 200
        assert b'name="username"' in response.content
        assert b'name="password"' in response.content

    def test_returns_400_when_idp_not_enabled(self):
        client = Client()
        mock_ts = _mock_tenant_settings(require_idp=False, idp_org_id="")
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.link_accounts.get_tenant_settings", return_value=mock_ts):
                response = client.get(_LINK_ACCOUNTS_URL)
        assert response.status_code == 400
        assert _IDP_NOT_ENABLED_MESSAGE.encode() in response.content

    def test_returns_400_on_org_scoped_site(self):
        client = Client()
        mock_ts = _mock_tenant_settings(require_idp=True, idp_org_id="org_rcuksa_abc123")
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.link_accounts.get_tenant_settings", return_value=mock_ts):
                response = client.get(_LINK_ACCOUNTS_URL)
        assert response.status_code == 400
        assert _IDP_NOT_ENABLED_MESSAGE.encode() in response.content


@pytest.mark.django_db
class TestLinkAccountsPostAuth:

    @pytest.fixture(autouse=True)
    def _tenant_mock(self, settings):
        settings.RATELIMIT_ENABLE = False
        mock_ts = _mock_tenant_settings(require_idp=True, idp_org_id="")
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.link_accounts.get_tenant_settings", return_value=mock_ts):
                yield mock_ts

    def test_valid_creds_redirects_to_account_linker(self):
        user = User.objects.create_user(username="linkme", password="secret123")
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "linkme", "password": "secret123"})

        assert response.status_code == 302
        location = response["Location"]
        assert location.startswith("/auth/account-linker/?session_ref=")

        session_ref = location.split("session_ref=", 1)[1]
        assert client.session[f"{SESSION_KEY_PREFIX}{session_ref}"] == str(user.id)

    def test_invalid_password_returns_400(self):
        User.objects.create_user(username="linkme2", password="correct")
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "linkme2", "password": "wrong"})

        assert response.status_code == 400
        assert _INVALID_CREDENTIALS_MESSAGE.encode() in response.content
        session_keys = [k for k in client.session.keys() if k.startswith(SESSION_KEY_PREFIX)]
        assert session_keys == []

    def test_unknown_username_returns_400(self):
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "nosuchuser", "password": "any"})

        assert response.status_code == 400
        assert _INVALID_CREDENTIALS_MESSAGE.encode() in response.content
        session_keys = [k for k in client.session.keys() if k.startswith(SESSION_KEY_PREFIX)]
        assert session_keys == []

    def test_inactive_user_returns_400(self):
        User.objects.create_user(username="inactiveuser", password="secret123", is_active=False)
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "inactiveuser", "password": "secret123"})

        assert response.status_code == 400
        assert _INVALID_CREDENTIALS_MESSAGE.encode() in response.content

    def test_nologin_user_returns_400(self):
        nologin_user = User.objects.create_user(username="nologinuser", password="secret123")
        nologin_user.is_nologin = True
        nologin_user.save(update_fields=["is_nologin"])
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "nologinuser", "password": "secret123"})

        assert response.status_code == 400
        assert _INVALID_CREDENTIALS_MESSAGE.encode() in response.content

    def test_nologin_and_already_linked_user_returns_generic_message(self):
        """is_nologin is checked before auth0_id — the stricter gate wins."""
        user = User.objects.create_user(username="nologin_linked", password="secret123")
        user.is_nologin = True
        user.auth0_id = "auth0|both_flags"
        user.save(update_fields=["is_nologin", "auth0_id"])
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "nologin_linked", "password": "secret123"})

        assert response.status_code == 400
        assert _INVALID_CREDENTIALS_MESSAGE.encode() in response.content
        assert _ALREADY_LINKED_MESSAGE.encode() not in response.content

    def test_already_linked_user_returns_400(self):
        linked_user = User.objects.create_user(username="alreadylinked", password="secret123")
        linked_user.auth0_id = "auth0|existing_sub"
        linked_user.save(update_fields=["auth0_id"])
        client = Client()

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "alreadylinked", "password": "secret123"})

        assert response.status_code == 400
        assert _ALREADY_LINKED_MESSAGE.encode() in response.content


@pytest.mark.django_db
class TestLinkAccountsRateLimit:

    @pytest.fixture(autouse=True)
    def _tenant_mock(self):
        mock_ts = _mock_tenant_settings(require_idp=True, idp_org_id="")
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.link_accounts.get_tenant_settings", return_value=mock_ts):
                yield mock_ts

    def test_username_rate_limit_blocks_after_5_requests(self):
        client = Client()
        for _ in range(5):
            client.post(_LINK_ACCOUNTS_URL, {"username": "ratelimituser", "password": "any"})

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "ratelimituser", "password": "any"})

        assert response.status_code == 403

    def test_username_rate_limit_is_case_insensitive(self):
        client = Client()
        for _ in range(3):
            client.post(_LINK_ACCOUNTS_URL, {"username": "testuser", "password": "any"})
        for _ in range(2):
            client.post(_LINK_ACCOUNTS_URL, {"username": "TestUser", "password": "any"})

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "TESTUSER", "password": "any"})

        assert response.status_code == 403

    def test_different_usernames_have_separate_buckets(self):
        client = Client()
        for _ in range(5):
            client.post(_LINK_ACCOUNTS_URL, {"username": "alice_rl", "password": "wrongpass"})

        response = client.post(_LINK_ACCOUNTS_URL, {"username": "bob_rl", "password": "any"})

        assert response.status_code != 403


@pytest.mark.django_db
class TestLinkAccountsCSRF:
    @pytest.fixture(autouse=True)
    def _disable_ratelimit(self, settings):
        settings.RATELIMIT_ENABLE = False

    def test_post_without_csrf_returns_403(self):
        mock_ts = _mock_tenant_settings(require_idp=True, idp_org_id="")
        client = Client(enforce_csrf_checks=True)

        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.link_accounts.get_tenant_settings", return_value=mock_ts):
                response = client.post(
                    _LINK_ACCOUNTS_URL,
                    {"username": "someone", "password": "anything"},
                )

        assert response.status_code == 403
