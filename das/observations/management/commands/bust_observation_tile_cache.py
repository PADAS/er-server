"""Bust observation segment / track vector tile cache for one tenant."""

from __future__ import annotations

import logging

from django_multitenant.utils import get_current_tenant

from django.core.management.base import BaseCommand, CommandError

from observations.tasks import bump_observation_segment_tile_cache_for_tenant_task
from utils.cache import (
    bump_observation_segment_tile_version,
    delete_tile_keys_by_prefix,
)
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Invalidate cached observation segment vector tiles for the current tenant.\n\n"
        "Default: synchronously bump the per-tenant segment tile version (O(1) Redis). "
        "Tile URLs embed that version, so clients miss cache without SCAN.\n\n"
        "--enqueue: queue the same bump on maintenance workers (useful if you avoid Redis "
        "writes from this pod, or want the bust to follow normal Celery retries/monitoring).\n\n"
        "--flush-keys: SCAN+DELETE all vt:{tenant_id}:… keys (heavy on Redis; use only for "
        "memory reclamation or rare corruption). Cannot be combined with --enqueue."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--enqueue",
            action="store_true",
            help="Queue bump_observation_segment_tile_cache_for_tenant_task instead of bumping locally.",
        )
        parser.add_argument(
            "--flush-keys",
            action="store_true",
            help="Also run Redis SCAN/DELETE for vt:{tenant_id}: (expensive; not for routine use).",
        )

    def handle(self, *args, **options):
        tenant = get_current_tenant()
        if not tenant:
            raise CommandError("No tenant set. Use --tenant_domain.")

        tenant_id = str(tenant.id)
        enqueue = options["enqueue"]
        flush_keys = options["flush_keys"]

        if enqueue and flush_keys:
            raise CommandError("--enqueue and --flush-keys cannot be used together (flush must run synchronously).")

        if enqueue:
            async_result = bump_observation_segment_tile_cache_for_tenant_task.apply_async(
                kwargs={"domain": tenant.domain},
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued segment tile cache bump for {tenant.domain} ({tenant_id}), task_id={async_result.id}."
                )
            )
            return

        try:
            if flush_keys:
                prefix = f"vt:{tenant_id}:"
                deleted = delete_tile_keys_by_prefix(prefix)
                self.stdout.write(
                    self.style.WARNING(f"Deleted {deleted} vector tile cache keys matching {prefix!r} (Redis SCAN).")
                )

            bump_observation_segment_tile_version(tenant_id)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Bumped observation segment tile version for {tenant.domain} ({tenant_id}). "
                    "New MVT requests will miss server-side cache."
                )
            )
        except Exception as e:
            logger.exception("Failed to bust observation vector tile cache for tenant %s", tenant_id)
            raise CommandError(f"Failed to bust observation vector tile cache: {e}") from e
