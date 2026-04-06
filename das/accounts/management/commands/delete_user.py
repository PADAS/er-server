from __future__ import annotations

import logging

import oauth2_provider.models as oauth_models

from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import accounts.models as account_models
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Permanently delete a user account. Only deletes accounts, oauth, and admin-log "
        "data. Refuses to proceed if the user has references in other apps (activity, "
        "observations, usercontent)."
    )

    def add_arguments(self, parser):
        lookup = parser.add_mutually_exclusive_group(required=True)
        lookup.add_argument("--username", type=str, help="Username of the user to delete")
        lookup.add_argument("--user-id", type=str, dest="user_id", help="UUID of the user to delete")

        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Show what would be deleted without making any changes (default: True).",
        )
        parser.add_argument(
            "--execute",
            action="store_false",
            dest="dry_run",
            help="Actually perform the deletion (required to make changes).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            default=False,
            help=(
                "Report whether the user can be deleted without modifying any records "
                "outside accounts, oauth tokens, and admin log entries. Exits 0 if clean, 1 if not."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Skip the confirmation prompt.",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options)

        self.stdout.write(f"User: {user.username} (id={user.id}, email={user.email})")

        blocking = _blocking_references(user)

        if options["check"]:
            if blocking:
                self.stdout.write(self.style.ERROR("Cannot delete — linked records exist:"))
                for label, count in blocking.items():
                    self.stdout.write(f"  {count:>6}  {label}")
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS("User can be deleted cleanly (no external references)."))
            return

        if blocking:
            self.stdout.write(self.style.ERROR("Cannot delete — user has references in other apps:"))
            for label, count in blocking.items():
                self.stdout.write(f"  {count:>6}  {label}")
            self.stdout.write("Remove these references first, then retry.")
            return

        self._print_impact(user)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes made."))
            return

        if not options["force"]:
            answer = input(f"Permanently delete user '{user.username}'? This cannot be undone. [yes/N] ")
            if answer.strip().lower() != "yes":
                self.stdout.write("Aborted.")
                return

        with transaction.atomic():
            _delete_user(user)

        self.stdout.write(self.style.SUCCESS(f"User '{user.username}' permanently deleted."))

    def _resolve_user(self, options):
        try:
            if options.get("user_id"):
                return account_models.User.objects.get(id=options["user_id"])
            return account_models.User.objects.get(username=options["username"])
        except account_models.User.DoesNotExist:
            identifier = options.get("user_id") or options.get("username")
            raise CommandError(f"User '{identifier}' not found.")

    def _print_impact(self, user):
        counts = {
            "oauth access tokens (deleted)": oauth_models.get_access_token_model().objects.filter(user=user).count(),
            "oauth refresh tokens (deleted)": oauth_models.get_refresh_token_model().objects.filter(user=user).count(),
            "oauth grants (deleted)": oauth_models.get_grant_model().objects.filter(user=user).count(),
            "admin log entries (deleted)": LogEntry.objects.filter(user=user).count(),
            "act-as profiles (deleted)": account_models.ActAsProfiles.objects.filter(from_user=user).count()
            + account_models.ActAsProfiles.objects.filter(to_user=user).count(),
            "user agreements (deleted)": account_models.UserAgreement.objects.filter(user=user).count(),
        }
        self.stdout.write("Impact summary:")
        for label, count in counts.items():
            if count:
                self.stdout.write(f"  {count:>6}  {label}")


def _blocking_references(user: account_models.User) -> dict[str, int]:
    """Return counts of records outside accounts/oauth/admin that reference this user.

    A non-empty result means the user cannot be deleted.
    """
    from activity.models import Event, EventNote, EventPhoto, PatrolFile, PatrolNote
    from observations.models import AnnouncementUser, GPXTrackFile, Source, Subject
    from usercontent.models import FileContent, ImageFileContent

    candidates = {
        "events (created_by_user)": Event.objects.filter(created_by_user=user).count(),
        "event notes (created_by_user)": EventNote.objects.filter(created_by_user=user).count(),
        "event photos (created_by_user)": EventPhoto.objects.filter(created_by_user=user).count(),
        "patrol notes (created_by_user)": PatrolNote.objects.filter(created_by_user=user).count(),
        "patrol files (created_by)": PatrolFile.objects.filter(created_by=user).count(),
        "sources (owner)": Source.objects.filter(owner=user).count(),
        "subjects (linked_user)": Subject.objects.filter(linked_user=user).count(),
        "subjects (owner)": Subject.objects.filter(owner=user).count(),
        "GPX track files (created_by)": GPXTrackFile.objects.filter(created_by=user).count(),
        "announcement users": AnnouncementUser.objects.filter(user=user).count(),
        "file contents (created_by)": FileContent.objects.filter(created_by=user).count(),
        "image file contents (created_by)": ImageFileContent.objects.filter(created_by=user).count(),
    }
    return {label: count for label, count in candidates.items() if count}


def _delete_user(user: account_models.User) -> None:
    """Permanently delete a user and related accounts/oauth/admin data."""
    pk = user.id

    # Clear M2M permission sets.
    user.permission_sets.clear()

    # Delete accounts-app related records.
    account_models.ActAsProfiles.objects.filter(from_user=user).delete()
    account_models.ActAsProfiles.objects.filter(to_user=user).delete()
    account_models.UserAgreement.objects.filter(user=user).delete()

    # Delete oauth tokens and grants.
    oauth_models.get_access_token_model().objects.filter(user_id=pk).delete()
    oauth_models.get_refresh_token_model().objects.filter(user_id=pk).delete()
    oauth_models.get_grant_model().objects.filter(user_id=pk).delete()

    # Delete admin log entries.
    LogEntry.objects.filter(user_id=pk).delete()

    # Use _raw_delete to bypass the soft-delete override on User.
    account_models.User.objects.filter(id=pk)._raw_delete(account_models.User.objects.filter(id=pk).db)
    logger.info("Permanently deleted user id=%s", pk)
