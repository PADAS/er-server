from __future__ import annotations

import logging
from typing import NamedTuple

from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db.models import Q

from accounts.account_linker import send_idp_invitation_email
from accounts.models import User
from accounts.system_users import SYSTEM_USERNAMES
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)

_DISALLOWED_USERNAMES = SYSTEM_USERNAMES + ["admin"]


class _InvitationSuccess(NamedTuple):
    username: str


class _InvitationFailure(NamedTuple):
    username: str
    exception_message: str


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Send EarthRanger Identity (Auth0) magic-link invitations to every active, "
        "unlinked user with an email on the specified tenant. Requires require_idp=True "
        "and a non-org-scoped site."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=("List users who would be emailed and the total count, " "but send nothing and make no writes."),
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        tenant_settings = get_tenant_settings()
        feature_flags = tenant_settings.feature_flags

        if not feature_flags.require_idp:
            raise CommandError("require_idp is not enabled for this tenant")

        org_id = feature_flags.idp_org_id
        if org_id and org_id.strip():
            raise CommandError(
                "This tenant is org-scoped (idp_org_id is set). "
                "Magic-link invitations are not supported on org-scoped sites — "
                "users are provisioned out-of-band via Auth0."
            )

        base_url = f"https://{tenant_settings.domain}"

        candidates = (
            User.objects.filter(
                is_active=True,
                is_nologin=False,
            )
            .filter(
                Q(auth0_id__isnull=True) | Q(auth0_id=""),
            )
            .exclude(email="")
            .exclude(email__isnull=True)
            .exclude(username__in=_DISALLOWED_USERNAMES)
            .order_by("username")
        )

        if dry_run:
            self._output_dry_run(candidates)
            return

        successes: list[_InvitationSuccess] = []
        failures: list[_InvitationFailure] = []

        for user in candidates:
            try:
                send_idp_invitation_email(user, base_url=base_url)
                successes.append(_InvitationSuccess(username=user.username))
                logger.info("Sent IDP invitation to user %s <%s>", user.username, user.email)
            except Exception as exc:
                failures.append(_InvitationFailure(username=user.username, exception_message=str(exc)))
                logger.exception("Failed to send IDP invitation to user %s", user.username)

        total = len(successes) + len(failures)
        self._output_results(successes, failures, total)

        if failures:
            raise CommandError(f"Failed to send invitations to {len(failures)} of {total} user(s)!")

    def _output_dry_run(self, candidates) -> None:
        users = list(candidates)
        if not users:
            self.stdout.write("DRY RUN: No eligible users found.")
            return
        self.stdout.write("DRY RUN: Would send invitations to:")
        for user in users:
            self.stdout.write(f"  {user.username}\t{user.email}")
        self.stdout.write(f"DRY RUN: Total: {len(users)} user(s) would be emailed.")

    def _output_results(
        self,
        successes: list[_InvitationSuccess],
        failures: list[_InvitationFailure],
        total: int,
    ) -> None:
        if successes:
            self.stdout.write(self.style.SUCCESS("SUCCESSFULLY SENT:"))
            self.stdout.write(self.style.SUCCESS("\n".join(s.username for s in successes)))
        if failures:
            self.stdout.write(self.style.ERROR("FAILED TO SEND:"))
            self.stdout.write(self.style.ERROR("\n".join(f"{f.username}\t{f.exception_message}" for f in failures)))
        self.stdout.write(f"Summary: {len(successes)} sent, {len(failures)} failed, {total} total.")
