from __future__ import annotations

import logging
import uuid
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django_multitenant.utils import set_current_tenant

from django.core.management import CommandError

from accounts.management.commands.clear_auth0_ids import Command
from accounts.models import User
from factories import PermissionSetFactory, TenantFactory


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestClearAuth0IdsCommand:
    """Management command clear_auth0_ids — clearing, dry-run, and typed confirmation."""

    @pytest.fixture(autouse=True)
    def mock_get_tenant_settings(self):
        """The command reads only the tenant domain, for its confirmation warning."""
        mock_settings = MagicMock()
        mock_settings.domain = "rcuksa.pamdas.org"
        with patch("accounts.management.commands.clear_auth0_ids.get_tenant_settings") as mock_get:
            mock_get.return_value = mock_settings
            yield mock_settings

    @pytest.fixture(autouse=True)
    def confirm_input(self):
        """By default the operator types the exact confirmation phrase."""
        with patch("builtins.input", return_value="I understand") as mock_input:
            yield mock_input

    @pytest.fixture
    def stdout(self):
        return StringIO()

    @pytest.fixture
    def command(self, stdout):
        return Command(stdout=stdout)

    def test_clears_auth0_id_on_all_users_with_a_non_null_auth0_id(self, command):
        User.objects.create_user(username="a", email="a@example.com", is_active=True, auth0_id="auth0|a")
        User.objects.create_user(username="b", email="b@example.com", is_active=True, auth0_id="auth0|b")

        command.handle(dry_run=False)

        assert User.objects.get(username="a").auth0_id is None
        assert User.objects.get(username="b").auth0_id is None

    def test_includes_system_and_admin_users(self, command):
        """Per the abandonment scope no username is exempt — admin and system users are cleared too."""
        User.objects.create_user(username="admin", email="admin@example.com", is_active=True, auth0_id="auth0|admin")
        User.objects.create_user(username="er_system", email="sys@example.com", is_active=True, auth0_id="auth0|sys")

        command.handle(dry_run=False)

        assert User.objects.get(username="admin").auth0_id is None
        assert User.objects.get(username="er_system").auth0_id is None

    def test_leaves_users_whose_auth0_id_is_already_null_untouched(self, command):
        User.objects.create_user(username="already-null", email="n@example.com", is_active=True, auth0_id=None)

        command.handle(dry_run=False)

        assert User.objects.get(username="already-null").auth0_id is None

    def test_preserves_site_membership_permissions_and_profile(self, command):
        """Only auth0_id is cleared — das_tenant, permission sets, and profile fields are untouched (AC#2)."""
        user = User.objects.create_user(
            username="keep-me",
            email="keep@example.com",
            is_active=True,
            is_staff=True,
            first_name="Keep",
            last_name="Me",
            auth0_id="auth0|keep",
        )
        permission_set = PermissionSetFactory.create()
        user.permission_sets.add(permission_set)
        original_tenant_id = user.das_tenant_id

        command.handle(dry_run=False)

        refreshed = User.objects.get(username="keep-me")
        assert refreshed.auth0_id is None
        assert refreshed.das_tenant_id == original_tenant_id
        assert list(refreshed.permission_sets.all()) == [permission_set]
        assert refreshed.is_staff is True
        assert refreshed.is_active is True
        assert refreshed.first_name == "Keep"
        assert refreshed.last_name == "Me"
        assert refreshed.email == "keep@example.com"

    def test_does_not_touch_auth0_ids_of_other_tenants(self, command):
        """The bulk clear must never cross the tenant boundary.

        A regression that dropped the manager's implicit ``das_tenant_id`` predicate on the
        UPDATE would null every tenant's auth0_id at once — the catastrophic failure mode this
        command is built to avoid. Prove the write stays inside the current tenant.
        """
        user_here = User.objects.create_user(
            username="here", email="here@example.com", is_active=True, auth0_id="auth0|here"
        )

        other_tenant = TenantFactory.create(id=uuid.uuid4(), domain=f"other-{uuid.uuid4().hex[:12]}.example.com")
        set_current_tenant(other_tenant)
        try:
            user_elsewhere = User.objects.create_user(
                username="elsewhere", email="elsewhere@example.com", is_active=True, auth0_id="auth0|elsewhere"
            )
        finally:
            set_current_tenant(self.das_tenant)

        command.handle(dry_run=False)

        assert User.objects.get(pk=user_here.pk).auth0_id is None

        set_current_tenant(other_tenant)
        try:
            assert User.objects.get(pk=user_elsewhere.pk).auth0_id == "auth0|elsewhere"
        finally:
            set_current_tenant(self.das_tenant)

    def test_aborts_and_makes_no_changes_when_confirmation_phrase_is_wrong(self, command, confirm_input):
        confirm_input.return_value = "no"
        User.objects.create_user(username="c", email="c@example.com", is_active=True, auth0_id="auth0|c")

        with pytest.raises(CommandError, match="Aborted"):
            command.handle(dry_run=False)

        assert User.objects.get(username="c").auth0_id == "auth0|c"

    def test_aborts_when_confirmation_is_empty(self, command, confirm_input):
        confirm_input.return_value = ""
        User.objects.create_user(username="empty", email="empty@example.com", is_active=True, auth0_id="auth0|empty")

        with pytest.raises(CommandError, match="Aborted"):
            command.handle(dry_run=False)

        assert User.objects.get(username="empty").auth0_id == "auth0|empty"

    def test_aborts_cleanly_when_stdin_is_not_a_tty(self, command, confirm_input):
        confirm_input.side_effect = EOFError
        User.objects.create_user(username="notty", email="notty@example.com", is_active=True, auth0_id="auth0|notty")

        with pytest.raises(CommandError, match="Aborted"):
            command.handle(dry_run=False)

        assert User.objects.get(username="notty").auth0_id == "auth0|notty"

    def test_confirmation_accepts_surrounding_whitespace(self, command, confirm_input):
        confirm_input.return_value = "  I understand  "
        User.objects.create_user(username="d", email="d@example.com", is_active=True, auth0_id="auth0|d")

        command.handle(dry_run=False)

        assert User.objects.get(username="d").auth0_id is None

    def test_warning_shows_tenant_domain_and_count(self, command, stdout):
        User.objects.create_user(username="e", email="e@example.com", is_active=True, auth0_id="auth0|e")

        command.handle(dry_run=False)

        lines = stdout.getvalue().splitlines()
        assert "WARNING: This will clear auth0_id on 1 user(s) on tenant 'rcuksa.pamdas.org'." in lines

    def test_reports_nothing_to_clear_and_does_not_prompt_when_no_users_have_auth0_id(
        self, command, confirm_input, stdout
    ):
        User.objects.create_user(username="unlinked", email="u@example.com", is_active=True, auth0_id=None)

        command.handle(dry_run=False)

        confirm_input.assert_not_called()
        assert "No users with an auth0_id found — nothing to clear." in stdout.getvalue().splitlines()

    def test_dry_run_makes_no_writes_and_does_not_prompt(self, command, confirm_input):
        User.objects.create_user(username="f", email="f@example.com", is_active=True, auth0_id="auth0|f")

        command.handle(dry_run=True)

        assert User.objects.get(username="f").auth0_id == "auth0|f"
        confirm_input.assert_not_called()

    def test_dry_run_lists_username_and_email(self, command, stdout):
        User.objects.create_user(
            username="dry-alice", email="dry-alice@example.com", is_active=True, auth0_id="auth0|alice"
        )

        command.handle(dry_run=True)

        lines = stdout.getvalue().splitlines()
        assert "DRY RUN: Would clear auth0_id on:" in lines
        assert "  dry-alice\tdry-alice@example.com\tauth0|alice" in lines
        assert "DRY RUN: Total: 1 user(s) would be cleared." in lines

    def test_dry_run_shows_no_email_placeholder_for_users_without_an_email(self, command, stdout):
        User.objects.create_user(username="no-email-user", is_active=True, auth0_id="auth0|noemail")

        command.handle(dry_run=True)

        lines = stdout.getvalue().splitlines()
        assert "  no-email-user\t(no email)\tauth0|noemail" in lines

    def test_dry_run_reports_zero_when_no_users_have_auth0_id(self, command, stdout):
        command.handle(dry_run=True)

        assert "DRY RUN: No users with an auth0_id found." in stdout.getvalue().splitlines()

    def test_real_run_reports_the_number_of_cleared_users(self, command, stdout):
        User.objects.create_user(username="s1", email="s1@example.com", is_active=True, auth0_id="auth0|s1")
        User.objects.create_user(username="s2", email="s2@example.com", is_active=True, auth0_id="auth0|s2")

        command.handle(dry_run=False)

        assert "Cleared auth0_id on 2 user(s)." in stdout.getvalue().splitlines()

    def test_aborts_when_the_preview_became_stale_before_the_clear(self, command, confirm_input):
        User.objects.create_user(username="stable", email="stable@example.com", is_active=True, auth0_id="auth0|stable")
        vanisher = User.objects.create_user(
            username="vanisher", email="vanisher@example.com", is_active=True, auth0_id="auth0|vanisher"
        )

        def clear_vanisher_then_confirm(*args, **kwargs):
            User.objects.filter(pk=vanisher.pk).update(auth0_id=None)
            return "I understand"

        confirm_input.side_effect = clear_vanisher_then_confirm

        with pytest.raises(CommandError, match="changed since the preview"):
            command.handle(dry_run=False)

        assert User.objects.get(username="stable").auth0_id == "auth0|stable"

    def test_real_run_logs_each_cleared_user_with_its_old_sub(self, command, caplog):
        User.objects.create_user(
            username="loguser", email="loguser@example.com", is_active=True, auth0_id="auth0|logsub"
        )

        with caplog.at_level(logging.INFO, logger="accounts.management.commands.clear_auth0_ids"):
            command.handle(dry_run=False)

        messages = [record.getMessage() for record in caplog.records]
        assert "Cleared auth0_id for user loguser <loguser@example.com> (was auth0|logsub)" in messages
