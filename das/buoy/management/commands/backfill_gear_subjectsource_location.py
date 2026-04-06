from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from buoy.constants import BUOY_DEVICE_SUBJECT_SUBTYPE, BUOY_GEAR_SUBJECT_SUBTYPE
from observations.models import (
    DEFAULT_ASSIGNED_RANGE,
    LatestObservationSource,
    SubjectSource,
)
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)

GEAR_SUBJECT_SUBTYPES = (BUOY_GEAR_SUBJECT_SUBTYPE, BUOY_DEVICE_SUBJECT_SUBTYPE)


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Backfill SubjectSource.location for gear subjects from LatestObservationSource. "
        "Run once after deploying the change that keeps SubjectSource.location current via BuoyService. "
        "Safe to delete once all environments have been migrated."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of SubjectSource rows to process per batch (default: 500).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be updated without writing to the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        batch_size: int = options["batch_size"]
        dry_run: bool = options["dry_run"]

        if dry_run:
            self.stdout.write("DRY RUN — no changes will be written.")

        max_upper = DEFAULT_ASSIGNED_RANGE[1]
        gear_ss_qs = SubjectSource.objects.filter(
            subject__subject_subtype__in=GEAR_SUBJECT_SUBTYPES,
            subject__is_active=True,
            assigned_range__endswith=max_upper,  # only currently deployed (open-ended range)
        )

        total = gear_ss_qs.count()
        self.stdout.write(f"Found {total} active (deployed) gear SubjectSource rows to backfill.")

        updated = 0
        skipped_no_obs = 0
        skipped_empty_point = 0
        batch_ss: list[SubjectSource] = []
        batch_source_ids: list[UUID] = []

        def flush(ss_list: list[SubjectSource]) -> None:
            if not ss_list or dry_run:
                return
            with transaction.atomic():
                SubjectSource.objects.bulk_update(ss_list, ["location"])

        for ss in gear_ss_qs.iterator(chunk_size=batch_size):
            batch_ss.append(ss)
            batch_source_ids.append(ss.source_id)

            if len(batch_ss) < batch_size:
                continue

            updated_ids, skipped_no_obs, skipped_empty_point = self._process_batch(
                batch_ss, batch_source_ids, skipped_no_obs, skipped_empty_point
            )
            flush([s for s in batch_ss if s.pk in updated_ids])
            updated += len(updated_ids)
            logger.info("Updated %d rows (running total: %d / %d).", len(updated_ids), updated, total)
            batch_ss = []
            batch_source_ids = []

        if batch_ss:
            updated_ids, skipped_no_obs, skipped_empty_point = self._process_batch(
                batch_ss, batch_source_ids, skipped_no_obs, skipped_empty_point
            )
            flush([s for s in batch_ss if s.pk in updated_ids])
            updated += len(updated_ids)

        self.stdout.write(
            f"Done. Updated: {updated}, "
            f"skipped (no observation): {skipped_no_obs}, "
            f"skipped (empty point / 0,0): {skipped_empty_point}."
        )

    @staticmethod
    def _process_batch(
        ss_list: list[SubjectSource],
        source_ids: list[UUID],
        skipped_no_obs: int,
        skipped_empty_point: int,
    ) -> tuple[set[UUID], int, int]:
        """Bulk-fetch LatestObservationSource for the batch and set location on matching rows."""
        los_by_source = {
            los.source_id: los
            for los in LatestObservationSource.objects.filter(source_id__in=source_ids).select_related("observation")
        }

        updated_ids: set[UUID] = set()
        for ss in ss_list:
            los = los_by_source.get(ss.source_id)
            if not los or not los.observation:
                skipped_no_obs += 1
                continue
            loc = los.observation.location
            if not loc or (loc.x == 0 and loc.y == 0):
                skipped_empty_point += 1
                continue
            ss.location = loc
            updated_ids.add(ss.pk)

        return updated_ids, skipped_no_obs, skipped_empty_point
