"""
Tests for the Account Linker feature.

Tests the PKCE OAuth flow that binds ER user accounts to Auth0 identities,
including magic link token generation/validation, the landing page view,
and the Auth0 callback view.
"""

import logging
from unittest.mock import Mock, patch

import pytest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.account_linker import (
    _EMAIL_COLLISION_MESSAGE,
    MAGIC_LINK_SALT,
    SESSION_KEY_PREFIX,
    account_linker_callback,
    account_linker_landing,
    already_linked_response,
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
        email="prioremail@example.com",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def mock_tenant_settings():
    with patch("accounts.account_linker.get_tenant_settings") as mock_ts:
        mock = Mock()
        mock.feature_flags.require_idp = True
        mock.feature_flags.idp_org_id = None
        mock.domain = "testsite.pamdas.org"
        mock.url = "https://testsite.pamdas.org"
        mock_ts.return_value = mock
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock):
            yield mock


@pytest.fixture(autouse=True)
def _bypass_lazy_auth0_client():
    """Park a mock OAuth client inside the lazy wrapper so that
    _ensure_registered() is never called during tests."""
    import accounts.account_linker as mod

    mod._account_linker_auth0_client._client = Mock()
    yield
    mod._account_linker_auth0_client._client = None


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


class TestAlreadyLinkedResponse:
    """The shared dialog helper used by both the landing and the self-service form.

    No @pytest.mark.django_db: the helper renders a static template and touches no DB.
    Non-cacheability is provided by the views' @never_cache, not the helper, so it is
    asserted on the view paths rather than here.
    """

    def test_renders_already_linked_dialog_at_409(self):
        response = already_linked_response()
        assert response.status_code == 409
        content = response.content.decode()
        assert "This account is already linked to EarthRanger Identity." in content
        assert content.count('<a class="button" href="/">Log in normally</a>') == 1


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
            mock_redirect.assert_called_once_with(
                request,
                "https://example.com/auth/account-linker/callback/",
                state=link_attempt,
                prompt="login",
            )

    def test_magic_link_reuse_after_linking_shows_already_linked_dialog(self, request_factory, active_user, caplog):
        token = create_magic_link_token(active_user.id)

        # Simulate the user having already completed the Account Linker flow
        active_user.auth0_id = "auth0|already_linked"
        active_user.save(update_fields=["auth0_id"])

        request = request_factory.get(f"/auth/account-linker/?token={token}")
        request.session = {}

        with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
            result = account_linker_landing(request)

        assert result.status_code == 409
        # Served from a single-use token/session_ref URL, so it must not be cached.
        assert "no-store" in result.headers.get("Cache-Control", "")
        content = result.content.decode()
        assert "This account is already linked to EarthRanger Identity." in content
        # exactly one "log in normally" CTA, linking to the ER Web root
        assert content.count('<a class="button" href="/">Log in normally</a>') == 1
        assert (
            f"Account linker landing for already-linked user {active_user.username} (auth0_id=auth0|already_linked)"
            in caplog.text
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
                prompt="login",
            )

    def test_session_flow_already_linked_user_shows_already_linked_dialog(self, request_factory, active_user, caplog):
        active_user.auth0_id = "auth0|already_linked"
        active_user.save(update_fields=["auth0_id"])

        session_ref = "caller-provided-ref"
        request = request_factory.get(f"/auth/account-linker/?session_ref={session_ref}")
        request.session = {f"{SESSION_KEY_PREFIX}{session_ref}": str(active_user.id)}

        with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
            result = account_linker_landing(request)

        assert result.status_code == 409
        # Served from a single-use token/session_ref URL, so it must not be cached.
        assert "no-store" in result.headers.get("Cache-Control", "")
        content = result.content.decode()
        assert "This account is already linked to EarthRanger Identity." in content
        # exactly one "log in normally" CTA, linking to the ER Web root
        assert content.count('<a class="button" href="/">Log in normally</a>') == 1
        assert (
            f"Account linker landing for already-linked user {active_user.username} (auth0_id=auth0|already_linked)"
            in caplog.text
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

    def test_landing_response_is_not_cacheable(self, request_factory):
        # The landing receives a single-use session_ref/token in its URL, so
        # its response must never be stored by a browser, proxy, or cache.
        request = request_factory.get("/auth/account-linker/")
        request.session = {}

        result = account_linker_landing(request)

        assert "no-store" in result.headers.get("Cache-Control", "")


@pytest.mark.django_db
class TestAccountLinkerCallback:

    def _make_mock_token(self, sub: str = "auth0|new_sub_123", email: str = "newauth0email@example.com"):
        token = Mock()
        token.get = lambda key, default=None: {"userinfo": {"sub": sub, "email": email}}.get(key, default)
        return token

    def test_successful_linking(self, request_factory, active_user):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        session_key = f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}"
        request.session = {session_key: str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token()

            result = account_linker_callback(request)

            active_user.refresh_from_db()
            assert active_user.auth0_id == "auth0|new_sub_123"
            assert result.status_code == 302
            assert result.url == "/"
            assert session_key not in request.session

    def test_successful_linking_writes_email(self, request_factory, active_user):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(email="newauth0email@example.com")

            result = account_linker_callback(request)

        assert result.status_code == 302
        active_user.refresh_from_db()
        assert active_user.email == "newauth0email@example.com"

    @pytest.mark.parametrize(
        "db_email, auth0_email",
        [
            ("taken@example.com", "taken@example.com"),
            ("taken@example.com", "Taken@Example.COM"),
            ("TAKEN@EXAMPLE.COM", "taken@example.com"),
            (" taken@example.com ", "taken@example.com"),
            ("taken@example.com", " taken@example.com "),
        ],
    )
    @pytest.mark.parametrize("is_active", [True, False])
    def test_email_collision_returns_400(self, request_factory, active_user, caplog, db_email, auth0_email, is_active):
        other_user = User.objects.create_user(
            username="collidinguser",
            email="placeholder@example.com",
            is_active=is_active,
        )
        # Force the exact db_email into the DB, bypassing create_user normalisation
        User.objects.filter(id=other_user.id).update(email=db_email)

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(email=auth0_email)

            with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
                result = account_linker_callback(request)

        assert result.status_code == 400
        assert result.content == _EMAIL_COLLISION_MESSAGE.encode()
        assert "Email collision during account linking" in caplog.text
        assert f"user '{active_user.username}'" in caplog.text
        assert f"user '{other_user.username}'" in caplog.text
        assert f"id={other_user.id}" in caplog.text
        assert f"active={is_active}" in caplog.text
        active_user.refresh_from_db()
        assert active_user.auth0_id is None

    @pytest.mark.parametrize(
        "userinfo",
        [
            {"sub": "auth0|new_sub_123"},
            {"sub": "auth0|new_sub_123", "email": None},
        ],
    )
    def test_missing_or_null_email_in_userinfo_returns_400(self, request_factory, active_user, caplog, userinfo):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        mock_token = Mock()
        mock_token.get = lambda key, default=None: {"userinfo": userinfo}.get(key, default)

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = mock_token

            with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
                result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Auth0 token missing email claim" in caplog.text

    def test_already_linked_matching_sub_updates_email(self, request_factory, active_user):
        active_user.auth0_id = "auth0|existing"
        active_user.save(update_fields=["auth0_id"])
        assert active_user.email == "prioremail@example.com"

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(sub="auth0|existing", email="newemail@example.com")

            result = account_linker_callback(request)

        assert result.status_code == 302
        active_user.refresh_from_db()
        assert active_user.email == "newemail@example.com"

    def test_already_linked_matching_sub_redirects(self, request_factory, active_user, caplog):
        active_user.auth0_id = "auth0|existing"
        active_user.save(update_fields=["auth0_id"])

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(sub="auth0|existing")

            with caplog.at_level(logging.INFO, logger="accounts.account_linker"):
                result = account_linker_callback(request)

        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|existing"
        assert result.status_code == 302
        assert result.url == "/"
        assert "already has auth0_id" in caplog.text

    def test_already_linked_mismatched_sub_returns_error(self, request_factory, active_user, caplog):
        active_user.auth0_id = "auth0|existing"
        active_user.save(update_fields=["auth0_id"])

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(sub="auth0|different")

            with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
                result = account_linker_callback(request)

        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|existing"
        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "Auth0 subject mismatch" in caplog.text

    def test_auth0_sub_already_linked_to_another_user_returns_error(self, request_factory, active_user, caplog):
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            is_active=True,
        )
        other_user.auth0_id = "auth0|taken_sub"
        other_user.save(update_fields=["auth0_id"])

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(sub="auth0|taken_sub")

            with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
                result = account_linker_callback(request)

        active_user.refresh_from_db()
        assert active_user.auth0_id is None
        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "already linked to another user" in caplog.text

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

    def test_callback_response_is_not_cacheable(self, request_factory):
        # The callback receives the OAuth code/state in its URL and must never
        # be stored by a browser, proxy, or cache.
        request = request_factory.get("/auth/account-linker/callback/")
        request.session = {}

        result = account_linker_callback(request)

        assert "no-store" in result.headers.get("Cache-Control", "")

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

    def test_missing_userinfo_returns_400(self, request_factory, active_user, caplog):
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
        assert "No userinfo in Auth0 token response" in caplog.text

    @pytest.mark.parametrize("bad_sub", [None, "", "  "])
    def test_null_or_empty_sub_claim_returns_400(self, request_factory, active_user, caplog, bad_sub):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        mock_token = Mock()
        mock_token.get = lambda key, default=None: {
            "userinfo": {"sub": bad_sub, "email": "newauth0email@example.com"}
        }.get(key, default)

        with caplog.at_level(logging.WARNING, logger="accounts.account_linker"):
            with patch(
                "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
            ) as mock_exchange:
                mock_exchange.return_value = mock_token
                result = account_linker_callback(request)

        assert result.status_code == 400
        assert b"Unable to associate your accounts" in result.content
        assert "missing or empty sub claim" in caplog.text

    def test_email_change_sends_notification_to_prior_address(self, request_factory, active_user):
        from django.core import mail

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(email="newauth0email@example.com")

            with patch(
                "accounts.account_linker.transaction.on_commit",
                side_effect=lambda func: func(),
            ):
                result = account_linker_callback(request)

        assert result.status_code == 302
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == ["prioremail@example.com"]
        assert msg.from_email == settings.DEFAULT_FROM_EMAIL
        assert "testsite.pamdas.org" in msg.subject
        # The new email address must not appear in either the text or HTML body
        assert "newauth0email@example.com" not in msg.body
        html_body, mime_type = msg.alternatives[0]
        assert mime_type == "text/html"
        assert "newauth0email@example.com" not in html_body

    def test_notification_strips_whitespace_from_prior_email(self, request_factory, active_user):
        from django.core import mail

        User.objects.filter(id=active_user.id).update(email=" prioremail@example.com ")

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(email="newauth0email@example.com")

            with patch(
                "accounts.account_linker.transaction.on_commit",
                side_effect=lambda func: func(),
            ):
                result = account_linker_callback(request)

        assert result.status_code == 302
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["prioremail@example.com"]

    def test_notification_send_failure_does_not_break_linking(self, request_factory, active_user, caplog):
        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(email="newauth0email@example.com")

            with patch(
                "django.core.mail.EmailMultiAlternatives.send",
                side_effect=Exception("SMTP connection refused"),
            ):
                with patch(
                    "accounts.account_linker.transaction.on_commit",
                    side_effect=lambda func: func(),
                ):
                    with caplog.at_level(logging.ERROR, logger="accounts.account_linker"):
                        result = account_linker_callback(request)

        assert result.status_code == 302
        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|new_sub_123"
        assert active_user.email == "newauth0email@example.com"
        assert "Failed to send email-changed notification" in caplog.text

    @pytest.mark.parametrize(
        "db_email, auth0_email",
        [
            ("prioremail@example.com", "prioremail@example.com"),
            ("PriorEmail@Example.com", "prioremail@example.com"),
            (" prioremail@example.com ", "prioremail@example.com"),
            ("   ", "newauth0email@example.com"),
        ],
    )
    def test_does_not_send_notification_for_non_substantive_change(
        self, request_factory, active_user, db_email, auth0_email
    ):
        from django.core import mail

        User.objects.filter(id=active_user.id).update(email=db_email)

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token(email=auth0_email)

            with patch(
                "accounts.account_linker.transaction.on_commit",
                side_effect=lambda func: func(),
            ):
                result = account_linker_callback(request)

        assert result.status_code == 302
        assert len(mail.outbox) == 0

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
        mock_ts.feature_flags.require_idp = False
        with patch("utils.tenant.decorators.get_tenant_settings", return_value=mock_ts):
            result = view_func(request)

        assert result.status_code == 400
        assert b"Account linking is not available for this site" in result.content

    @pytest.mark.parametrize(
        "view_func, path",
        [
            (account_linker_landing, "/auth/account-linker/"),
            (account_linker_callback, "/auth/account-linker/callback/"),
        ],
    )
    def test_org_scoped_site_returns_400(self, request_factory, mock_tenant_settings, view_func, path):
        """Both views must reject requests when the tenant has an idp_org_id set."""
        mock_tenant_settings.feature_flags.idp_org_id = "org_rcuksa_abc123"

        request = request_factory.get(path)
        request.session = {}

        result = view_func(request)

        assert result.status_code == 400
        assert b"Account linking is not available for this site" in result.content

    @pytest.mark.parametrize("blank_org_id", [None, "", "  "])
    def test_blank_org_id_allows_landing_to_initiate_pkce(
        self, request_factory, active_user, mock_tenant_settings, blank_org_id
    ):
        """A None, empty, or whitespace-only idp_org_id does not block the landing view."""
        mock_tenant_settings.feature_flags.idp_org_id = blank_org_id

        token = create_magic_link_token(active_user.id)
        request = request_factory.get(f"/auth/account-linker/?token={token}")
        request.session = {}
        request.build_absolute_uri = lambda path: f"https://example.com{path}"

        with patch("accounts.account_linker._account_linker_auth0_client.auth0.authorize_redirect") as mock_redirect:
            mock_redirect.return_value = HttpResponse("auth0_redirect")
            result = account_linker_landing(request)

        assert result.content == b"auth0_redirect"
        mock_redirect.assert_called_once()

    @pytest.mark.parametrize("blank_org_id", [None, "", "  "])
    def test_blank_org_id_allows_successful_linking(
        self, request_factory, active_user, mock_tenant_settings, blank_org_id
    ):
        """A None, empty, or whitespace-only idp_org_id does not block the callback view."""
        mock_tenant_settings.feature_flags.idp_org_id = blank_org_id

        request = request_factory.get(f"/auth/account-linker/callback/?state={FAKE_LINK_ATTEMPT}")
        request.session = {f"{SESSION_KEY_PREFIX}{FAKE_LINK_ATTEMPT}": str(active_user.id)}

        with patch(
            "accounts.account_linker._account_linker_auth0_client.auth0.authorize_access_token"
        ) as mock_exchange:
            mock_exchange.return_value = self._make_mock_token()
            result = account_linker_callback(request)

        assert result.status_code == 302
        active_user.refresh_from_db()
        assert active_user.auth0_id == "auth0|new_sub_123"
