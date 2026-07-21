from __future__ import annotations

import logging
from typing import NamedTuple

from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db.models import Q, QuerySet

from accounts.models import User
from accounts.system_users import SYSTEM_USERNAMES
from utils.auth0.guardian import send_guardian_otp_enrollment_ticket
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

_DISALLOWED_USERNAMES = SYSTEM_USERNAMES + ["admin"]

logger = logging.getLogger(__name__)


class _MintSuccess(NamedTuple):
    username: str


class _MintFailure(NamedTuple):
    username: str
    exception_message: str


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Mint Auth0 Guardian OTP enrollment tickets for every active, Auth0-linked user on "
        "the specified tenant so they can enrol an MFA factor. Requires require_idp=True and "
        "a non-org-scoped site."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="List the users who would be sent an enrollment ticket, but mint nothing.",
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        feature_flags = get_tenant_settings().feature_flags

        if not feature_flags.require_idp:
            raise CommandError("require_idp is not enabled for this tenant")

        org_id = feature_flags.idp_org_id
        if org_id and org_id.strip():
            raise CommandError(
                "This tenant is org-scoped (idp_org_id is set). Guardian enrollment tickets are not "
                "supported on org-scoped sites — users are provisioned out-of-band via Auth0."
            )

        candidates = (
            User.objects.filter(is_active=True, is_nologin=False)
            .exclude(Q(auth0_id__isnull=True) | Q(auth0_id=""))
            .exclude(username__in=_DISALLOWED_USERNAMES)
            .order_by("username")
        )

        if dry_run:
            self._output_dry_run(candidates)
            return

        successes: list[_MintSuccess] = []
        failures: list[_MintFailure] = []

        for user in candidates:
            try:
                send_guardian_otp_enrollment_ticket(user.auth0_id)
                successes.append(_MintSuccess(username=user.username))
                logger.info("Minted MFA enrollment ticket for user %s", user.username)
            except Exception as exc:
                failures.append(_MintFailure(username=user.username, exception_message=str(exc)))
                logger.exception("Failed to mint MFA enrollment ticket for user %s", user.username)

        total = len(successes) + len(failures)
        self._output_results(successes, failures, total)

        if failures:
            raise CommandError(f"Failed to mint enrollment tickets for {len(failures)} of {total} user(s)!")

    def _output_results(
        self,
        successes: list[_MintSuccess],
        failures: list[_MintFailure],
        total: int,
    ) -> None:
        if successes:
            self.stdout.write(self.style.SUCCESS("SUCCESSFULLY MINTED:"))
            self.stdout.write(self.style.SUCCESS("\n".join(s.username for s in successes)))
        if failures:
            self.stdout.write(self.style.ERROR("FAILED TO MINT:"))
            self.stdout.write(self.style.ERROR("\n".join(f"{f.username}\t{f.exception_message}" for f in failures)))
        self.stdout.write(f"Summary: {len(successes)} minted, {len(failures)} failed, {total} total.")

    def _output_dry_run(self, candidates: QuerySet[User]) -> None:
        users = list(candidates)
        if not users:
            self.stdout.write("DRY RUN: No eligible users found.")
            return
        self.stdout.write("DRY RUN: Would mint enrollment tickets for:")
        for user in users:
            self.stdout.write(f"  {user.username}")
        self.stdout.write(f"DRY RUN: Total: {len(users)} user(s) would be sent a ticket.")
