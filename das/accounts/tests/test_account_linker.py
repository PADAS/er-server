"""
Tests for the Account Linker feature.

Tests the PKCE OAuth flow that binds ER user accounts to Auth0 identities,
including magic link token generation/validation, the landing page view,
and the Auth0 callback view.
"""

import logging
from unittest.mock import Mock, patch

import pytest

from django.contrib.auth import get_user_model
from django.core import signing
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.account_linker import (
    MAGIC_LINK_SALT,
    SESSION_KEY_PREFIX,
    account_linker_callback,
    account_linker_landing,
    create_magic_link_token,
    resolve_user_from_magic_link_token,
)

FAKE_LINK_ATTEMPT = "test-link-attempt"

User = get_user_model()


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def active_user():
    return User.objects.create_user(
        username="linkuser",
        email="link@example.com",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def mock_tenant_settings():
    with patch("accounts.account_linker.get_tenant_settings") as mock_ts:
        mock = Mock()
        mock.feature_flags.require_idp = True
        mock.feature_flags.idp_org_id = "org_test456"
        mock.url = "https://testsite.pamdas.org"
        mock_ts.return_value = mock
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock):
            yield mock


@pytest.mark.django_db
class TestMagicLinkTokens:

    def test_create_and_resolve_roundtrip(self, active_user):
        token = create_magic_link_token(active_user.id)
        resolved = resolve_user_from_magic_link_token(token)
        assert resolved.id == active_user.id

    def test_expired_token_raises(self, active_user):
        creation_time = 1_000_000
        with patch("django.core.signing.time.time", return_value=creation_time):
            token = create_magic_link_token(active_user.id)
        with patch("accounts.account_linker.settings") as mock_settings:
            mock_settings.ACCOUNT_LINKER_MAGIC_LINK_MAX_AGE_SECONDS = 0
            with patch("django.core.signing.time.time", return_value=creation_time + 1):
                with pytest.raises(signing.SignatureExpired):
                    resolve_user_from_magic_link_token(token)

    def test_tampered_token_raises(self, active_user):
        token = create_magic_link_token(active_user.id)
        tampered = token + "x"
        with pytest.raises(signing.BadSignature):
            resolve_user_from_magic_link_token(tampered)

    def test_nonexistent_user_raises(self):
        token = signing.dumps({"user_id": "00000000-0000-0000-0000-000000000000"}, salt=MAGIC_LINK_SALT)
        with pytest.raises(User.DoesNotExist):
            resolve_user_from_magic_link_token(token)


@pytest.mark.django_db
class TestAccountLinkerLanding:

    def test_magic_link_valid_token_initiates_pkce(self, request_factory, active_user):
        token = create_magic_link_token(active_user.id)
        request = request_factory.get(f"/auth/account-linker/?token={token}")
        request.session = {}
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.account_linker._account_linker_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            result = account_linker_landing(request)

            assert result.content == b"auth0_redirect"
            # Verify user_id stored under a link_attempt-keyed session entry
            session_entries = {k: v for k, v in request.session.items() if k.startswith(SESSION_KEY_PREFIX)}
            assert len(session_entries) == 1
            link_attempt = list(session_entries.keys())[0].removeprefix(SESSION_KEY_PREFIX)
            assert session_entries[f"{SESSION_KEY_PREFIX}{link_attempt}"] == str(active_user.id)
            # Verify state= passed to authorize_redirect
            mock_redirect.assert_called_once_with(
                request,
                "https://example.com/auth/account-linker/callback/",
                state=link_attempt,
            )

    def test_magic_link_expired_token_returns_400(self, request_factory, active_user):
        creation_time = 1_000_000
        with patch("django.core.signing.time.time", return_value=creation_time):
            token = create_magic_link_token(active_user.id)
        request = request_factory.get(f"/auth/account-linker/?token={token}")
        request.session = {}

        with patch("accounts.account_linker.settings") as mock_settings:
            mock_settings.ACCOUNT_LINKER_MAGIC_LINK_MAX_AGE_SECONDS = 0
            with patch("django.core.signing.time.time", return_value=creation_time + 1):
                result = account_linker_landing(request)

        assert result.status_code == 400
        assert b"expired" in result.content

    def test_magic_link_tampered_token_returns_400(self, request_factory, caplog):
        request = request_factory.get("/auth/account-linker/?token=tampered.garbage.value")
        request.session = {}

        with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
            result = account_linker_landing(request)

        assert result.status_code == 400
        assert b"Invalid link" in result.content
        assert "Error resolving user from magic link token" in caplog.text

    def test_session_flow_valid_user_initiates_pkce(self, request_factory, active_user):
        session_ref = "caller-provided-ref"
        request = request_factory.get(f"/auth/account-linker/?session_ref={session_ref}")
        request.session = {f"{SESSION_KEY_PREFIX}{session_ref}": str(active_user.id)}
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.account_linker._account_linker_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")

            result = account_linker_landing(request)

            assert result.content == b"auth0_redirect"
            # Caller's session_ref should be consumed; a new link_attempt created
            assert f"{SESSION_KEY_PREFIX}{session_ref}" not in request.session
            session_entries = {k: v for k, v in request.session.items() if k.startswith(SESSION_KEY_PREFIX)}
            assert len(session_entries) == 1
            link_attempt = list(session_entries.keys())[0].removeprefix(SESSION_KEY_PREFIX)
            assert session_entries[f"{SESSION_KEY_PREFIX}{link_attempt}"] == str(active_user.id)
            mock_redirect.assert_called_once_with(
                request,
                "https://example.com/auth/account-linker/callback/",
                state=link_attempt,
            )

    def test_missing_token_and_no_session_returns_400(self, request_factory, caplog):
        request = request_factory.get("/auth/account-linker/")
        request.session = {}

        with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
            result = account_linker_landing(request)

        assert result.status_code == 400
        assert b"Invalid link. Please contact your site administrator" in result.content
        assert "Account linker landing reached without token or valid session_ref" in caplog.text

    def test_session_flow_nonexistent_user_returns_400(self, request_factory, caplog):
        session_ref = "caller-provided-ref"
        request = request_factory.get(f"/auth/account-linker/?session_ref={session_ref}")
        request.session = {f"{SESSION_KEY_PREFIX}{session_ref}": "00000000-0000-0000-0000-000000000000"}

        with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
            result = account_linker_landing(request)

        assert result.status_code == 400
        assert b"Invalid link. Please contact your site administrator" in result.content
        assert "Account linker session_ref contained unknown or inactive user_id" in caplog.text


@pytest.mark.django_db
class TestAccountLinkerCallback:

    def _make_mock_token(self, sub="auth0|new_sub_123"):
        token = Mock()
        token.get = lambda key, default=None: {"userinfo": {"sub": sub}}.get(key, default)
        return token

    def test_successful_linking(self, request_factory, active_user, mock_tenant_settings):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        session_key = f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}"
        request.session = {session_key: str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            with patch("accounts.account_linker._add_user_to_auth0_org") as mock_add_org:
                mock_exchange.return_value = self._make_mock_token()

                result = account_linker_callback(request)

                active_user.refresh_from_db()
                assert active_user.auth0_id == "auth0|new_sub_123"
                mock_add_org.assert_called_once_with("auth0|new_sub_123", "org_test456")
                assert result.status_code == 302
                assert result.url == "/"
                assert session_key not in request.session

    def test_already_linked_matching_sub_adds_to_org(self, request_factory, active_user, mock_tenant_settings, caplog):
        active_user.auth0_id = "auth0|existing"
        active_user.save(update_fields=["auth0_id"])

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            with patch("accounts.account_linker._add_user_to_auth0_org") as mock_add_org:
                mock_exchange.return_value = self._make_mock_token(sub="auth0|existing")

                with caplog.at_level(logging.INFO, logger="accounts.account_linker"):
                    result = account_linker_callback(request)

        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|existing"
        mock_add_org.assert_called_once_with("auth0|existing", "org_test456")
        assert result.status_code == 302
        assert result.url == "/"
        assert "already has auth0_id" in caplog.text

    def test_already_linked_mismatched_sub_returns_error(
        self, request_factory, active_user, mock_tenant_settings, caplog
    ):
        active_user.auth0_id = "auth0|existing"
        active_user.save(update_fields=["auth0_id"])

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            with patch("accounts.account_linker._add_user_to_auth0_org") as mock_add_org:
                mock_exchange.return_value = self._make_mock_token(sub="auth0|different")

                with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
                    result = account_linker_callback(request)

        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|existing"
        mock_add_org.assert_not_called()
        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Auth0 subject mismatch" in caplog.text

    def test_user_not_found_returns_error(self, request_factory, caplog):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": "00000000-0000-0000-0000-000000000000"}

        with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
            with patch(
                "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
            ) as mock_exchange:
                mock_exchange.return_value = self._make_mock_token()
                result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "not found during account linker callback" in caplog.text

    def test_auth0_error_returns_400(self, request_factory, caplog):
        request = request_factory.get(
            f"/auth/account-linker/callback/?error=access_denied&error_description=User+cancelled&state={FAKE_LINK_ATTEMPT}"
        )
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": "some-id"}

        with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
            result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Auth0 returned error during account linking: access_denied - User cancelled" in caplog.text

    def test_missing_link_attempt_returns_400(self, request_factory, caplog):
        request = request_factory.get("/auth/account-linker/callback/")
        request.session = {}

        with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
            result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "No valid link_attempt in session during account linker callback" in caplog.text

    def test_token_exchange_failure_returns_400(self, request_factory, active_user, caplog):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
            with patch(
                "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token",
                side_effect=Exception("exchange failed"),
            ):
                result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Error exchanging authorization code in account linker" in caplog.text

    def test_missing_sub_claim_returns_400(self, request_factory, active_user, caplog):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        mock_token = Mock()
        mock_token.get = lambda key, default=None: default  # No userinfo

        with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
            with patch(
                "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
            ) as mock_exchange:
                mock_exchange.return_value = mock_token

                result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Could not extract sub claim from Auth0 token" in caplog.text

    def test_org_membership_failure_saves_auth0_id_but_returns_error(
        self, request_factory, active_user, mock_tenant_settings, caplog
    ):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
            with patch(
                "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
            ) as mock_exchange:
                with patch(
                    "accounts.account_linker._add_user_to_auth0_org",
                    side_effect=Exception("Management API error"),
                ):
                    mock_exchange.return_value = self._make_mock_token()

                    result = account_linker_callback(request)

        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|new_sub_123"
        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Failed to add user" in caplog.text

    @pytest.mark.parametrize(
        "view_func, path",
        [
            (account_linker_landing, "/auth/account-linker/"),
            (account_linker_callback, "/auth/account-linker/callback/"),
        ],
    )
    def test_idp_not_configured_returns_error(self, request_factory, view_func, path):
        request = request_factory.get(path)
        request.session = {}

        mock_ts = Mock()
        mock_ts.feature_flags.require_idp = True
        mock_ts.feature_flags.idp_org_id = None
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            result = view_func(request)

        assert result.status_code == 400
        assert b"Account linking is not available for this site" in result.content
