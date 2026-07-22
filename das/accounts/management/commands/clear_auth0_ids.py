from __future__ import annotations

import logging

from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)

_CONFIRMATION_PHRASE = "I understand"


class Command(TenantCommandMixin, BaseCommand):
    help = "Clear the Auth0 identity link (auth0_id) on the current tenant's users."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="List the users whose auth0_id would be cleared, but make no writes.",
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        preview: list[tuple[str, str | None, str]] = list(
            User.objects.filter(auth0_id__isnull=False)
            .order_by("username")
            .values_list("username", "email", "auth0_id")
        )

        if dry_run:
            self._report_dry_run(preview)
            return

        if not preview:
            self.stdout.write("No users with an auth0_id found — nothing to clear.")
            return

        domain = get_tenant_settings().domain
        self.stdout.write(f"WARNING: This will clear auth0_id on {len(preview)} user(s) on tenant '{domain}'.")
        self.stdout.write("This unlinks their Auth0 identity and cannot be undone by this command.")
        try:
            response = input(f'Type "{_CONFIRMATION_PHRASE}" to continue: ')
        except EOFError:
            response = ""
        if response.strip() != _CONFIRMATION_PHRASE:
            raise CommandError("Aborted — no changes made.")

        # Lock and re-read the set inside one transaction, then refuse to proceed if it drifted from
        # the preview the operator reviewed — we only ever clear the exact set that was confirmed.
        with transaction.atomic():
            current: list[tuple[str, str | None, str]] = list(
                User.objects.select_for_update()
                .filter(auth0_id__isnull=False)
                .order_by("username")
                .values_list("username", "email", "auth0_id")
            )
            if current != preview:
                raise CommandError(
                    f"Aborted — the set of users changed since the preview "
                    f"({len(preview)} previewed, {len(current)} now). Re-run to review the current set."
                )
            updated = User.objects.filter(auth0_id__isnull=False).update(auth0_id=None)

        for username, email, auth0_id in current:
            logger.info("Cleared auth0_id for user %s <%s> (was %s)", username, email, auth0_id)
        self.stdout.write(f"Cleared auth0_id on {updated} user(s).")

    def _report_dry_run(self, rows: list[tuple[str, str | None, str]]) -> None:
        if not rows:
            self.stdout.write("DRY RUN: No users with an auth0_id found.")
            return
        self.stdout.write("DRY RUN: Would clear auth0_id on:")
        for username, email, auth0_id in rows:
            self.stdout.write(f"  {username}\t{email or '(no email)'}\t{auth0_id}")
        self.stdout.write(f"DRY RUN: Total: {len(rows)} user(s) would be cleared.")
