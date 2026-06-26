from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from django.core import mail
from django.core.management import CommandError

from accounts.management.commands.send_idp_invitations import Command
from accounts.models import User


def _make_tenant_settings(
    *, require_idp: bool = True, idp_org_id: str | None = None, domain: str = "testsite.pamdas.org"
):
    mock_feature_flags = MagicMock()
    mock_feature_flags.require_idp = require_idp
    mock_feature_flags.idp_org_id = idp_org_id

    mock_settings = MagicMock()
    mock_settings.feature_flags = mock_feature_flags
    mock_settings.domain = domain
    return mock_settings


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSendIdpInvitationsCommand:
    """Management command send_idp_invitations — guards, filtering, email sending, and dry-run."""

    @pytest.fixture(autouse=True)
    def mock_get_tenant_settings(self):
        """Patch get_tenant_settings used by the command module."""
        mock_settings = _make_tenant_settings()
        with patch("accounts.management.commands.send_idp_invitations.get_tenant_settings") as mock_get:
            mock_get.return_value = mock_settings
            self._tenant_settings = mock_settings
            yield mock_settings

    @pytest.fixture(autouse=True)
    def mock_account_linker_tenant_settings(self):
        """Patch get_tenant_settings used inside send_idp_invitation_email (account_linker module)."""
        mock_settings = _make_tenant_settings()
        with patch("accounts.account_linker.get_tenant_settings") as mock_get:
            mock_get.return_value = mock_settings
            yield mock_settings

    @pytest.fixture
    def stdout(self):
        return StringIO()

    @pytest.fixture
    def command(self, stdout):
        return Command(stdout=stdout)

    # ------------------------------------------------------------------
    # Tenant-level guards
    # ------------------------------------------------------------------

    def test_raises_command_error_when_require_idp_is_false(self, command):
        """When require_idp is False the command aborts immediately, no emails sent."""
        self._tenant_settings.feature_flags.require_idp = False

        with pytest.raises(CommandError, match="require_idp is not enabled"):
            command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_raises_command_error_when_site_is_org_scoped(self, command):
        """When idp_org_id is set the command aborts — org-scoped sites use out-of-band provisioning."""
        self._tenant_settings.feature_flags.idp_org_id = "org_rcuksa_abc123"

        with pytest.raises(CommandError, match="org-scoped"):
            command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_does_not_block_when_org_id_is_whitespace_only(self, command):
        """An idp_org_id of pure whitespace is treated as absent (not org-scoped) per policy."""
        self._tenant_settings.feature_flags.idp_org_id = "   "

        # No users → completes without error and sends nothing.
        command.handle(dry_run=False)
        assert len(mail.outbox) == 0

    # ------------------------------------------------------------------
    # Happy path — correct users get emailed
    # ------------------------------------------------------------------

    def test_sends_invitation_to_active_unlinked_user_with_email(self, command):
        """An active, unlinked user with an email address receives exactly one invitation."""
        User.objects.create_user(
            username="unlinked-user",
            email="unlinked@example.com",
            is_active=True,
        )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["unlinked@example.com"]

    def test_skips_linked_user(self, command):
        """A user with auth0_id set (already linked) receives no invitation."""
        User.objects.create_user(
            username="linked-user",
            email="linked@example.com",
            is_active=True,
            auth0_id="auth0|already-linked",
        )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_sends_invitation_to_user_with_null_auth0_id(self, command):
        """A user whose auth0_id is None (the canonical unlinked state) receives an invitation."""
        User.objects.create_user(
            username="null-auth0-id-user",
            email="null@example.com",
            is_active=True,
            auth0_id=None,
        )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["null@example.com"]

    def test_skips_inactive_user(self, command):
        """An inactive user receives no invitation."""
        User.objects.create_user(
            username="inactive-user",
            email="inactive@example.com",
            is_active=False,
        )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_skips_nologin_user(self, command):
        """A no-login user (is_nologin=True) receives no invitation even when active, unlinked, and has an email."""
        User.objects.create_user(
            username="nologin-user",
            email="nologin@example.com",
            is_active=True,
            is_nologin=True,
        )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_skips_user_with_no_email(self, command):
        """A user without an email address receives no invitation."""
        User.objects.create_user(
            username="no-email-user",
            is_active=True,
        )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_skips_system_and_admin_usernames(self, command):
        """System usernames and 'admin' are excluded from invitations regardless of other attributes.

        Creates only system users that are not pre-seeded into the test database
        (username+tenant uniqueness). The important contract being tested is that
        the ORM filter excludes ALL of SYSTEM_USERNAMES + ["admin"], so we verify
        it by creating a representative subset that is safe to insert.
        """
        # er_system, system_analyzers, gfwwebhookuser, and deleted are NOT
        # pre-seeded into the test tenant; admin and das_oauth_act may be.
        for username in ["er_system", "system_analyzers", "gfwwebhookuser", "deleted"]:
            User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                is_active=True,
            )

        command.handle(dry_run=False)

        assert len(mail.outbox) == 0

    def test_sends_to_multiple_eligible_users(self, command):
        """All eligible users on the tenant receive exactly one invitation each."""
        User.objects.create_user(username="alice", email="alice@example.com", is_active=True)
        User.objects.create_user(username="bob", email="bob@example.com", is_active=True)
        # These must be excluded:
        User.objects.create_user(username="linked", email="linked@example.com", is_active=True, auth0_id="auth0|x")
        User.objects.create_user(username="inactive", email="inactive@example.com", is_active=False)
        User.objects.create_user(username="no-email", is_active=True)
        User.objects.create_user(username="admin", email="admin@example.com", is_active=True)

        command.handle(dry_run=False)

        recipients = {msg.to[0] for msg in mail.outbox}
        assert recipients == {"alice@example.com", "bob@example.com"}
        assert len(mail.outbox) == 2

    def test_invitation_url_contains_tenant_domain_and_token(self, command):
        """The invitation URL appears in both the plaintext body and the HTML alternative."""
        User.objects.create_user(username="tokenuser", email="tokenuser@example.com", is_active=True)

        command.handle(dry_run=False)

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        # plaintext part
        assert "testsite.pamdas.org" in msg.body
        assert "token=" in msg.body
        # HTML alternative
        html_body, mime_type = msg.alternatives[0]
        assert mime_type == "text/html"
        assert "testsite.pamdas.org" in html_body
        assert "token=" in html_body

    def test_email_is_multipart_with_html_alternative(self, command):
        """The sent email is multipart/alternative with exactly one text/html part."""
        User.objects.create_user(username="multipart-user", email="multipart@example.com", is_active=True)

        command.handle(dry_run=False)

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert len(msg.alternatives) == 1
        _, mime_type = msg.alternatives[0]
        assert mime_type == "text/html"

    def test_html_part_contains_cta_href_and_wordmark(self, command):
        """The HTML part contains the CTA link href and the EarthRanger wordmark."""
        User.objects.create_user(username="html-user", email="html@example.com", is_active=True)

        command.handle(dry_run=False)

        html_body, _ = mail.outbox[0].alternatives[0]
        assert "EarthRanger" in html_body
        # CTA button href — the invitation_url appears as an href in the HTML
        assert 'href="' in html_body
        assert "token=" in html_body

    # ------------------------------------------------------------------
    # Resilience — per-user send failures are collected, not fatal
    # ------------------------------------------------------------------

    def test_per_user_failure_is_collected_and_raises_at_end(self, command, stdout):
        """A send failure on one user is logged and collected; the command raises CommandError at the end."""
        User.objects.create_user(username="will-fail", email="fail@example.com", is_active=True)
        User.objects.create_user(username="will-succeed", email="succeed@example.com", is_active=True)

        call_count = 0

        def flaky_send(user, *, base_url):
            nonlocal call_count
            call_count += 1
            if user.username == "will-fail":
                raise RuntimeError("SMTP timeout")
            # actually enqueue a real email for the other user
            from accounts.account_linker import send_idp_invitation_email as real_send

            real_send(user, base_url=base_url)

        with patch(
            "accounts.management.commands.send_idp_invitations.send_idp_invitation_email", side_effect=flaky_send
        ):
            with pytest.raises(CommandError, match="Failed to send invitations to 1"):
                command.handle(dry_run=False)

        assert call_count == 2
        output = stdout.getvalue()
        assert "will-fail" in output
        assert "SMTP timeout" in output

    # ------------------------------------------------------------------
    # Dry-run mode
    # ------------------------------------------------------------------

    def test_dry_run_sends_no_emails(self, command):
        """With --dry-run no emails are dispatched."""
        User.objects.create_user(username="dry-user", email="dry@example.com", is_active=True)

        command.handle(dry_run=True)

        assert len(mail.outbox) == 0

    def test_dry_run_lists_eligible_users_in_output(self, command, stdout):
        """With --dry-run the eligible usernames and emails appear in stdout."""
        User.objects.create_user(username="dry-alice", email="dry-alice@example.com", is_active=True)
        User.objects.create_user(username="dry-bob", email="dry-bob@example.com", is_active=True)
        # Excluded — should NOT appear:
        User.objects.create_user(username="dry-linked", email="linked@example.com", is_active=True, auth0_id="auth0|x")

        command.handle(dry_run=True)

        output = stdout.getvalue()
        assert "dry-alice" in output
        assert "dry-bob" in output
        assert "dry-linked" not in output
        assert "DRY RUN" in output

    def test_dry_run_reports_zero_users_when_none_eligible(self, command, stdout):
        """With --dry-run and no eligible users the output says none were found."""
        command.handle(dry_run=True)

        output = stdout.getvalue()
        assert "No eligible users found" in output

    # ------------------------------------------------------------------
    # Shared helper: send_idp_invitation_email URL construction
    # ------------------------------------------------------------------

    def test_send_idp_invitation_email_builds_url_from_base_url(self):
        """send_idp_invitation_email constructs the invitation URL from the supplied base_url,
        and the URL appears in both the plaintext body and the HTML alternative."""
        from accounts.account_linker import send_idp_invitation_email

        user = User.objects.create_user(username="urltest", email="urltest@example.com", is_active=True)
        base_url = "https://testsite.pamdas.org"

        send_idp_invitation_email(user, base_url=base_url)

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        # plaintext body must contain the tenant domain and token
        assert "https://testsite.pamdas.org/" in msg.body
        assert "token=" in msg.body
        # HTML alternative must also carry the invitation URL
        html_body, mime_type = msg.alternatives[0]
        assert mime_type == "text/html"
        assert "https://testsite.pamdas.org/" in html_body
        assert "token=" in html_body
