"""Rebuild ``activity_tsvectormodel.tsvector_event`` for one site or all sites.

Migration ``0205_remove_schema_from_tsvector_triggers`` (ERA-13500) removed the
event type's JSON schema from the event search vector, so a schema's choice
labels no longer match a text search on every event of that type. The migration
only fixes the triggers; rows already in the table keep their polluted vector
until the event is touched again.

This command is the post-deploy step that repairs them. It is deliberately kept
out of the migration graph so a long-running table walk never sits in the deploy
path, and so it can be re-run later to rebuild a site's vectors on demand.

Tenant scoping
--------------
Deliberately cross-tenant, so no ``TenantCommandMixin`` (same reasoning as
``restore_clobbered_event_type_schemas``): ``--all-tenants`` has to reach rows
the thread's tenant context would hide. ``--tenant_domain`` resolves the site's
``DASTenant`` and pins every statement to its id via raw SQL predicates rather
than relying on ORM tenant scoping. One of the two modes must be given; there is
no implicit "everything" default.

Usage
-----
    # One site
    python manage.py rebuild_event_tsvectors --tenant_domain <domain>

    # Every site on the cluster
    python manage.py rebuild_event_tsvectors --all-tenants

    # Smaller batches (e.g. to keep statement times down on a busy cluster)
    python manage.py rebuild_event_tsvectors --all-tenants --batch-size 500

The walk is batched with keyset pagination and each batch is its own statement,
so the command is safe to interrupt: re-running it simply recomputes from the
start. Rebuilding a row is idempotent.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection

from activity.tsvector_rebuild import DEFAULT_BATCH_SIZE, rebuild_event_tsvectors
from core.models import DASTenant
from utils.tenant.managers import UnsetDASTenantContextManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Rebuild activity_tsvectormodel.tsvector_event from current event data, "
        "dropping the event type schema text that migration 0205 stopped indexing "
        "(ERA-13500). Target one site with --tenant_domain or every site with "
        "--all-tenants. Deliberately cross-tenant (no TenantCommandMixin)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--tenant_domain",
            type=str,
            default=None,
            help="Domain of the single site to rebuild, e.g. sandbox.pamdas.org.",
        )
        parser.add_argument(
            "--all-tenants",
            action="store_true",
            dest="all_tenants",
            help="Rebuild every site's rows. Required to touch more than one tenant.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Rows per batch/statement (default {DEFAULT_BATCH_SIZE}).",
        )

    def handle(self, *args: object, **options: object) -> None:
        # ``**options`` is a plain option dict, so every lookup is statically just
        # ``object`` and the checker cannot see the types argparse already coerced
        # these to in ``add_arguments``. Narrowing per value, with the reason each
        # suppression is needed; ``int()`` is kept as a runtime coercion because
        # ``call_command(..., batch_size="1")`` bypasses argparse's ``type=int``.
        tenant_domain: str | None = options["tenant_domain"]  # type: ignore[assignment]  # object is not str | None
        all_tenants: bool = bool(options["all_tenants"])
        batch_size: int = int(options["batch_size"])  # type: ignore[arg-type]  # int() has no object overload

        if not tenant_domain and not all_tenants:
            raise CommandError("Specify a single site with --tenant_domain, or pass --all-tenants.")
        if tenant_domain and all_tenants:
            raise CommandError("Pass either --tenant_domain or --all-tenants, not both.")
        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1.")

        das_tenant_id = self._resolve_tenant_id(tenant_domain) if tenant_domain else None
        target = f"site {tenant_domain} ({das_tenant_id})" if tenant_domain else "all sites"
        self.stdout.write(f"Rebuilding event tsvectors for {target}, batch size {batch_size}...")

        rows_updated = rebuild_event_tsvectors(
            connection,
            das_tenant_id=das_tenant_id,
            batch_size=batch_size,
            progress_callback=self._report_progress,
        )

        self.stdout.write(self.style.SUCCESS(f"Done. Rebuilt {rows_updated} event tsvector row(s) for {target}."))

    def _resolve_tenant_id(self, tenant_domain: str) -> str:
        """Look up the site's tenant id, ignoring any ambient tenant scoping.

        ``DASTenant`` is itself a tenant-scoped model keyed on its own ``id``, so
        an unscoped lookup by domain has to run with the thread's tenant unset --
        the same approach ``TenantCommandMixin`` uses.
        """
        try:
            with UnsetDASTenantContextManager():
                das_tenant = DASTenant.objects.get(domain=tenant_domain)
        except DASTenant.DoesNotExist:
            raise CommandError(f"No site found with domain '{tenant_domain}'.")
        except DASTenant.MultipleObjectsReturned:
            raise CommandError(f"More than one site has domain '{tenant_domain}'; cannot target it unambiguously.")
        return str(das_tenant.id)

    def _report_progress(self, rows_updated: int, batches: int) -> None:
        self.stdout.write(f"  ... {rows_updated} row(s) rebuilt across {batches} batch(es)")
