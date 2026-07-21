from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from django.core.management import CommandError

from accounts.management.commands.bulk_mint_mfa_enrollment_tickets import Command
from accounts.models import User


def _make_tenant_settings(*, require_idp: bool = True, idp_org_id: str | None = None):
    mock_feature_flags = MagicMock()
    mock_feature_flags.require_idp = require_idp
    mock_feature_flags.idp_org_id = idp_org_id

    mock_settings = MagicMock()
    mock_settings.feature_flags = mock_feature_flags
    return mock_settings


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestBulkMintMfaEnrollmentTicketsCommand:
    """Management command bulk_mint_mfa_enrollment_tickets — guards, candidate filtering, minting, dry-run."""

    @pytest.fixture(autouse=True)
    def mock_get_tenant_settings(self):
        """Patch get_tenant_settings used by the command module."""
        mock_settings = _make_tenant_settings()
        with patch("accounts.management.commands.bulk_mint_mfa_enrollment_tickets.get_tenant_settings") as mock_get:
            mock_get.return_value = mock_settings
            self._tenant_settings = mock_settings
            yield mock_settings

    @pytest.fixture
    def stdout(self):
        return StringIO()

    @pytest.fixture
    def command(self, stdout):
        return Command(stdout=stdout)

    @pytest.fixture
    def mock_mint(self):
        """Patch the Guardian enrollment-ticket mint so tests observe calls without hitting Auth0."""
        with patch(
            "accounts.management.commands.bulk_mint_mfa_enrollment_tickets.send_guardian_otp_enrollment_ticket"
        ) as mock_send:
            yield mock_send

    def test_raises_command_error_when_require_idp_is_false(self, command):
        """When require_idp is False the command aborts immediately."""
        self._tenant_settings.feature_flags.require_idp = False

        with pytest.raises(CommandError, match="require_idp is not enabled"):
            command.handle(dry_run=False)

    def test_raises_command_error_when_site_is_org_scoped(self, command):
        """When idp_org_id is set the command aborts — org-scoped sites use out-of-band provisioning."""
        self._tenant_settings.feature_flags.idp_org_id = "org_abc123"

        with pytest.raises(CommandError, match="org-scoped"):
            command.handle(dry_run=False)

    def test_does_not_block_when_org_id_is_whitespace_only(self, command):
        """An idp_org_id of pure whitespace is treated as absent (not org-scoped)."""
        self._tenant_settings.feature_flags.idp_org_id = "   "

        command.handle(dry_run=False)

    def test_mints_ticket_for_active_linked_user(self, command, mock_mint):
        """An active, Auth0-linked user gets exactly one ticket minted for their auth0_id."""
        User.objects.create_user(username="linked-user", is_active=True, auth0_id="auth0|linked123")

        command.handle(dry_run=False)

        mock_mint.assert_called_once_with("auth0|linked123")

    def test_skips_inactive_user(self, command, mock_mint):
        """An inactive user gets no ticket even when linked."""
        User.objects.create_user(username="inactive-user", is_active=False, auth0_id="auth0|inactive")

        command.handle(dry_run=False)

        mock_mint.assert_not_called()

    def test_skips_system_usernames(self, command, mock_mint):
        """System usernames are excluded even when active and linked.

        Uses system usernames that are not pre-seeded into the test tenant so they
        are safe to insert; the contract is that the ORM filter excludes them all.
        """
        for username in ["er_system", "system_analyzers", "gfwwebhookuser", "deleted"]:
            User.objects.create_user(username=username, is_active=True, auth0_id=f"auth0|{username}")

        command.handle(dry_run=False)

        mock_mint.assert_not_called()

    def test_skips_nologin_user(self, command, mock_mint):
        """A no-login user is skipped even when active and linked."""
        User.objects.create_user(username="nologin-user", is_active=True, is_nologin=True, auth0_id="auth0|nologin")

        command.handle(dry_run=False)

        mock_mint.assert_not_called()

    def test_per_user_failure_is_collected_and_command_raises(self, command, mock_mint, stdout):
        """A mint failure on one user does not abort the run; the command raises CommandError at the end."""
        User.objects.create_user(username="will-fail", is_active=True, auth0_id="auth0|will-fail")
        User.objects.create_user(username="will-succeed", is_active=True, auth0_id="auth0|will-succeed")

        def flaky_mint(auth0_id):
            if auth0_id == "auth0|will-fail":
                raise RuntimeError("Auth0 boom")

        mock_mint.side_effect = flaky_mint

        with pytest.raises(CommandError, match="Failed to mint"):
            command.handle(dry_run=False)

        attempted = {call.args[0] for call in mock_mint.call_args_list}
        assert attempted == {"auth0|will-fail", "auth0|will-succeed"}
        output = stdout.getvalue()
        assert "will-fail" in output
        assert "Auth0 boom" in output

    def test_prints_summary_on_success(self, command, mock_mint, stdout):
        """A successful run reports how many tickets were minted, failed, and considered."""
        User.objects.create_user(username="alice", is_active=True, auth0_id="auth0|alice")
        User.objects.create_user(username="bob", is_active=True, auth0_id="auth0|bob")

        command.handle(dry_run=False)

        output = stdout.getvalue()
        assert "2 minted" in output
        assert "0 failed" in output

    def test_dry_run_mints_nothing(self, command, mock_mint):
        """With --dry-run no tickets are minted."""
        User.objects.create_user(username="dry-user", is_active=True, auth0_id="auth0|dry")

        command.handle(dry_run=True)

        mock_mint.assert_not_called()

    def test_dry_run_lists_eligible_users_and_total(self, command, stdout):
        """With --dry-run the output lists exactly the eligible usernames, sorted, with their total."""
        User.objects.create_user(username="dry-alice", is_active=True, auth0_id="auth0|alice")
        User.objects.create_user(username="dry-bob", is_active=True, auth0_id="auth0|bob")
        User.objects.create_user(username="dry-unlinked", is_active=True)

        command.handle(dry_run=True)

        assert stdout.getvalue().splitlines() == [
            "DRY RUN: Would mint enrollment tickets for:",
            "  dry-alice",
            "  dry-bob",
            "DRY RUN: Total: 2 user(s) would be sent a ticket.",
        ]

    def test_dry_run_reports_no_eligible_users(self, command, stdout):
        """With --dry-run and no eligible users the output says none were found."""
        command.handle(dry_run=True)

        assert stdout.getvalue().splitlines() == ["DRY RUN: No eligible users found."]

    def test_logs_each_successful_mint(self, command, mock_mint, caplog):
        """Each successful mint emits exactly one INFO log naming the user."""
        User.objects.create_user(username="log-user", is_active=True, auth0_id="auth0|log")

        logger_name = "accounts.management.commands.bulk_mint_mfa_enrollment_tickets"
        with caplog.at_level(logging.INFO, logger=logger_name):
            command.handle(dry_run=False)

        mint_logs = [
            record
            for record in caplog.records
            if record.name == logger_name and record.levelno == logging.INFO and "log-user" in record.getMessage()
        ]
        assert len(mint_logs) == 1
