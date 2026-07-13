from __future__ import annotations

import pytest

from django.core.management import CommandError, call_command

from accounts.models import User


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestCreateTenantSuperuserCommand:
    """Management command createtenantsuperuser — the --email option added on top of Django's
    stock createsuperuser (which has no email support, since the User model's USERNAME_FIELD
    is "username" and REQUIRED_FIELDS is empty)."""

    def test_sets_email_when_username_and_email_are_both_given_noninteractively(self) -> None:
        """--email is applied to the created user when --username is supplied explicitly."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "newadmin",
            "--email",
            "newadmin@example.com",
            "--noinput",
        )

        user = User.objects.get(username="newadmin")
        assert user.email == "newadmin@example.com"
        assert user.is_superuser is True

    def test_leaves_email_empty_when_email_option_is_omitted(self) -> None:
        """Omitting --email is not a regression: the created user simply has no email set."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "noemailadmin",
            "--noinput",
        )

        user = User.objects.get(username="noemailadmin")
        assert not user.email

    def test_raises_command_error_when_email_given_without_explicit_username(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--email cannot be resolved to a user when the username instead comes from the
        DJANGO_SUPERUSER_USERNAME environment variable, since Django's createsuperuser never
        writes the resolved username back into `options`. The command raises a clear
        CommandError rather than silently dropping the email."""
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "envadmin")

        with pytest.raises(CommandError, match="--email requires --username"):
            call_command("createtenantsuperuser", "--email", "env@example.com", "--noinput")

        assert not User.objects.filter(username="envadmin").exists()

    @pytest.mark.parametrize("empty_email", ["", "   "], ids=["empty", "whitespace-only"])
    def test_raises_command_error_for_empty_or_whitespace_only_email(self, empty_email: str) -> None:
        """An explicitly-supplied empty or whitespace-only --email is rejected with a
        CommandError and no user is created, matching the User model's clean() rule that
        null is fine but blank/whitespace is not, and mirroring --auth0_id's handling."""
        with pytest.raises(CommandError, match="--email cannot be empty or whitespace-only"):
            call_command(
                "createtenantsuperuser",
                "--username",
                "blankemailadmin",
                "--email",
                empty_email,
                "--noinput",
            )

        assert not User.objects.filter(username="blankemailadmin").exists()

    def test_raises_command_error_for_invalid_email_format(self) -> None:
        """An invalid --email value is rejected with a CommandError, not silently saved."""
        with pytest.raises(CommandError):
            call_command(
                "createtenantsuperuser",
                "--username",
                "bademailadmin",
                "--email",
                "not-an-email",
                "--noinput",
            )

        assert not User.objects.filter(username="bademailadmin").exists()

    def test_validation_failures_do_not_create_any_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both failure modes are caught before super().handle() runs, so the command is
        atomic: no superuser is left behind, even without knowing its username in advance."""
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "envadmin")
        user_count_before = User.objects.count()

        with pytest.raises(CommandError, match="--email requires --username"):
            call_command("createtenantsuperuser", "--email", "env@example.com", "--noinput")

        assert User.objects.count() == user_count_before

        with pytest.raises(CommandError):
            call_command(
                "createtenantsuperuser",
                "--username",
                "bademailadmin",
                "--email",
                "not-an-email",
                "--noinput",
            )

        assert User.objects.count() == user_count_before

    def test_sets_auth0_id_when_username_and_auth0_id_are_both_given_noninteractively(
        self,
    ) -> None:
        """--auth0_id is applied to the created user when --username is supplied explicitly."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "auth0admin",
            "--auth0_id",
            "auth0|abc123",
            "--noinput",
        )

        user = User.objects.get(username="auth0admin")
        assert user.auth0_id == "auth0|abc123"
        assert user.is_superuser is True

    def test_sets_email_and_auth0_id_together(self) -> None:
        """--email and --auth0_id can both be supplied and are saved in the same update."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "bothadmin",
            "--email",
            "bothadmin@example.com",
            "--auth0_id",
            "auth0|both123",
            "--noinput",
        )

        user = User.objects.get(username="bothadmin")
        assert user.email == "bothadmin@example.com"
        assert user.auth0_id == "auth0|both123"

    def test_leaves_auth0_id_empty_when_auth0_id_option_is_omitted(self) -> None:
        """Omitting --auth0_id is not a regression: the created user simply has no auth0_id."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "noauth0admin",
            "--noinput",
        )

        user = User.objects.get(username="noauth0admin")
        assert not user.auth0_id

    def test_raises_command_error_for_whitespace_only_auth0_id(self) -> None:
        """A whitespace-only --auth0_id is rejected with a CommandError and no user is created,
        matching the User model's clean() rule that null is fine but blank/whitespace is not."""
        with pytest.raises(CommandError, match="--auth0_id cannot be empty or whitespace-only"):
            call_command(
                "createtenantsuperuser",
                "--username",
                "blankauth0admin",
                "--auth0_id",
                "   ",
                "--noinput",
            )

        assert not User.objects.filter(username="blankauth0admin").exists()

    def test_raises_command_error_when_auth0_id_given_without_explicit_username(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--auth0_id cannot be resolved to a user when the username instead comes from the
        DJANGO_SUPERUSER_USERNAME environment variable, mirroring the --email behaviour."""
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "envauth0admin")

        with pytest.raises(CommandError, match="--auth0_id requires --username"):
            call_command("createtenantsuperuser", "--auth0_id", "auth0|env123", "--noinput")

        assert not User.objects.filter(username="envauth0admin").exists()

    def test_raises_command_error_when_both_flags_given_without_explicit_username(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The requires-username error message names both flags when both are supplied."""
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "envbothadmin")

        with pytest.raises(CommandError, match=r"--email / --auth0_id requires --username"):
            call_command(
                "createtenantsuperuser",
                "--email",
                "envboth@example.com",
                "--auth0_id",
                "auth0|envboth123",
                "--noinput",
            )

        assert not User.objects.filter(username="envbothadmin").exists()

    def test_raises_command_error_for_duplicate_auth0_id_before_creating_user(self) -> None:
        """A duplicate --auth0_id is rejected before the new user is created (pre-checked
        ahead of super().handle()), rather than surfacing as a post-creation IntegrityError."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "originalauth0admin",
            "--auth0_id",
            "auth0|dup123",
            "--noinput",
        )
        user_count_before = User.objects.count()

        with pytest.raises(CommandError, match="already exists for this tenant"):
            call_command(
                "createtenantsuperuser",
                "--username",
                "duplicateauth0admin",
                "--auth0_id",
                "auth0|dup123",
                "--noinput",
            )

        assert User.objects.count() == user_count_before
        assert not User.objects.filter(username="duplicateauth0admin").exists()

    def test_raises_command_error_for_duplicate_email_before_creating_user(self) -> None:
        """A duplicate --email is rejected before the new user is created, mirroring the
        auth0_id pre-check, rather than surfacing as a post-creation IntegrityError."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "originalemailadmin",
            "--email",
            "dup@example.com",
            "--noinput",
        )
        user_count_before = User.objects.count()

        with pytest.raises(CommandError, match="already exists for this tenant"):
            call_command(
                "createtenantsuperuser",
                "--username",
                "duplicateemailadmin",
                "--email",
                "dup@example.com",
                "--noinput",
            )

        assert User.objects.count() == user_count_before
        assert not User.objects.filter(username="duplicateemailadmin").exists()

    def test_raises_command_error_for_existing_username_without_update(self) -> None:
        """An already-existing --username is rejected with a clear CommandError (not a raw
        IntegrityError) when --update is not passed, and no new row is created."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "existingadmin",
            "--noinput",
        )
        user_count_before = User.objects.count()

        with pytest.raises(CommandError, match="A user with username 'existingadmin' already exists"):
            call_command(
                "createtenantsuperuser",
                "--username",
                "existingadmin",
                "--noinput",
            )

        assert User.objects.count() == user_count_before

    def test_update_requires_explicit_username(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--update cannot be resolved to a user when the username comes from the
        DJANGO_SUPERUSER_USERNAME environment variable, mirroring --email/--auth0_id."""
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "envupdateadmin")

        with pytest.raises(CommandError, match="--update requires --username"):
            call_command("createtenantsuperuser", "--update", "--noinput")

        assert not User.objects.filter(username="envupdateadmin").exists()

    def test_update_on_missing_username_creates_normally(self) -> None:
        """--update on a --username that doesn't exist yet is an idempotent upsert: it falls
        through to normal creation instead of erroring."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "freshupdateadmin",
            "--email",
            "freshupdateadmin@example.com",
            "--update",
            "--noinput",
        )

        user = User.objects.get(username="freshupdateadmin")
        assert user.email == "freshupdateadmin@example.com"
        assert user.is_superuser is True
        assert user.is_staff is True

    def test_update_on_existing_user_sets_fields_and_forces_superuser_flags(self) -> None:
        """--update on an existing user applies --email/--auth0_id, forces is_superuser and
        is_staff to True, and leaves the password untouched."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "updatetarget",
            "--noinput",
        )
        user_before = User.objects.get(username="updatetarget")
        user_before.is_superuser = False
        user_before.is_staff = False
        user_before.save(update_fields=["is_superuser", "is_staff"])
        password_hash_before = user_before.password
        user_count_before = User.objects.count()

        call_command(
            "createtenantsuperuser",
            "--username",
            "updatetarget",
            "--email",
            "updatetarget@example.com",
            "--auth0_id",
            "auth0|updatetarget",
            "--update",
            "--noinput",
        )

        assert User.objects.count() == user_count_before
        user_after = User.objects.get(username="updatetarget")
        assert user_after.email == "updatetarget@example.com"
        assert user_after.auth0_id == "auth0|updatetarget"
        assert user_after.is_superuser is True
        assert user_after.is_staff is True
        assert user_after.password == password_hash_before

    def test_update_with_no_email_or_auth0_id_on_new_username_succeeds(self) -> None:
        """--update with neither --email nor --auth0_id, on a --username that doesn't exist
        yet, falls through to normal creation. The post-create branch then has no fields to
        update (update_fields would be empty), so it must not attempt user.save(update_fields=[])
        unconditionally; re-running the identical command must also succeed idempotently."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "bareupdateadmin",
            "--update",
            "--noinput",
        )

        user = User.objects.get(username="bareupdateadmin")
        assert user.is_superuser is True
        assert user.is_staff is True
        user_count_before = User.objects.count()

        call_command(
            "createtenantsuperuser",
            "--username",
            "bareupdateadmin",
            "--update",
            "--noinput",
        )

        assert User.objects.count() == user_count_before

    def test_raises_command_error_for_duplicate_email_differing_only_in_case_before_creating_user(
        self,
    ) -> None:
        """The email-uniqueness pre-check normalizes the candidate email before comparing it
        against existing rows, matching the normalization applied to the value that actually
        gets saved. Without that, an existing 'dup@example.com' row would not be found by a
        pre-check against the un-normalized 'dup@EXAMPLE.com', and the new user would be
        created by super().handle() before the later save() hit the DB's unique constraint."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "originalcaseemailadmin",
            "--email",
            "dup@example.com",
            "--noinput",
        )
        user_count_before = User.objects.count()

        with pytest.raises(CommandError, match="already exists for this tenant"):
            call_command(
                "createtenantsuperuser",
                "--username",
                "duplicatecaseemailadmin",
                "--email",
                "dup@EXAMPLE.com",
                "--noinput",
            )

        assert User.objects.count() == user_count_before
        assert not User.objects.filter(username="duplicatecaseemailadmin").exists()

    def test_update_is_idempotent_when_rerun_with_same_values(self) -> None:
        """Re-running the same --update command with identical --email/--auth0_id succeeds
        rather than tripping the uniqueness pre-checks against the user's own row."""
        call_command(
            "createtenantsuperuser",
            "--username",
            "idempotentadmin",
            "--email",
            "idempotentadmin@example.com",
            "--auth0_id",
            "auth0|idempotent",
            "--update",
            "--noinput",
        )
        user_count_before = User.objects.count()

        call_command(
            "createtenantsuperuser",
            "--username",
            "idempotentadmin",
            "--email",
            "idempotentadmin@example.com",
            "--auth0_id",
            "auth0|idempotent",
            "--update",
            "--noinput",
        )

        assert User.objects.count() == user_count_before
        user = User.objects.get(username="idempotentadmin")
        assert user.email == "idempotentadmin@example.com"
        assert user.auth0_id == "auth0|idempotent"
