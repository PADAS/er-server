import logging
import uuid
from typing import Optional

from psycopg2.extras import DateTimeTZRange

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from observations import models
from observations.tasks import maintain_subjectstatus_for_subject
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    """
    Delete observations older than a datetime, filtered either by a Source or a Subject.

    Examples:
        python manage.py trim_observations --tenant_domain example.com --source-id <uuid> --before 2025-01-01T00:00:00Z
        python manage.py trim_observations --tenant_domain example.com --subject-id <uuid> --before 2025-01-01T00:00:00Z
    """

    logger = logging.getLogger(__name__)
    help = "Trim observations older than a given datetime for a source or a subject."

    def add_arguments(self, parser):
        parser.add_argument(
            "--before",
            required=True,
            type=str,
            help="Delete observations with recorded_at strictly before this datetime (ISO-8601).",
        )

        filter_group = parser.add_mutually_exclusive_group(required=True)
        filter_group.add_argument(
            "--source-id",
            type=str,
            help="Source UUID. Deletes observations for that source with recorded_at < --before.",
        )
        filter_group.add_argument(
            "--source-manufacturer-id",
            type=str,
            help="Source manufacturer_id. Deletes observations for that source with recorded_at < --before.",
        )
        filter_group.add_argument(
            "--subject-id",
            type=str,
            help=(
                "Subject UUID. Deletes observations for sources assigned to the subject at the observation time "
                "(SubjectSource.assigned_range contains Observation.recorded_at) with recorded_at < --before."
            ),
        )

        parser.add_argument(
            "--batch-size",
            type=int,
            default=10000,
            help="Delete observations in batches (default: 10000).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="No deletion; only log what would be deleted.",
        )

    def handle(self, *args, **options):
        before = self._parse_before(options["before"])
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        if batch_size <= 0:
            raise CommandError("--batch-size must be a positive integer")

        source_id = self._parse_uuid_optional(options.get("source_id"))
        subject_id = self._parse_uuid_optional(options.get("subject_id"))
        source_manufacturer_id = options.get("source_manufacturer_id")

        # Resolve --source-manufacturer-id to a source_id up-front so the queryset
        # builder and the post-delete enqueue logic both work off a single resolved
        # source.
        if source_manufacturer_id:
            sources = models.Source.objects.filter(manufacturer_id=source_manufacturer_id)
            if not sources.exists():
                self.logger.info(f"No Source found with manufacturer_id={source_manufacturer_id!r}. Nothing to do.")
                return
            if sources.count() > 1:
                raise CommandError(f"Source manufacturer_id={source_manufacturer_id!r} is not unique for this tenant.")
            source_id = sources.first().id

        qs = self._build_queryset(before=before, source_id=source_id, subject_id=subject_id)

        scope = f"source_id={source_id}" if source_id else f"subject_id={subject_id}"
        self.logger.info(
            f"Trimming observations where recorded_at < {before.isoformat()} for {scope} (dry_run={dry_run})"
        )

        deleted = self._delete_in_batches(qs, batch_size=batch_size, dry_run=dry_run)
        self.logger.info(f"Done. {'Would delete' if dry_run else 'Deleted'} {deleted} observation(s).")

        if dry_run:
            return

        # Reconcile SubjectStatus only for subjects whose observations were
        # actually trimmed. Two modes:
        #   --subject-id  -> exactly that subject.
        #   --source-id / --source-manufacturer-id -> subjects assigned to that
        #     source during the trimmed window (assigned_range overlaps
        #     (-inf, before)). Avoids fanning out to every subject ever
        #     assigned to the source.
        if subject_id:
            affected_subject_ids = [subject_id]
        else:
            affected_subject_ids = list(
                models.SubjectSource.objects.filter(
                    source_id=source_id,
                    assigned_range__overlap=DateTimeTZRange(None, before),
                )
                .values_list("subject_id", flat=True)
                .distinct()
            )

        if affected_subject_ids:
            for sid in affected_subject_ids:
                maintain_subjectstatus_for_subject.apply_async(args=(str(sid),))
            self.logger.info(f"Queued maintain_subjectstatus_for_subject for {len(affected_subject_ids)} subject(s).")

    def _parse_before(self, value: str):
        dt = parse_datetime(value)
        if dt is None:
            raise CommandError(f"--before value {value!r} is not a valid datetime string (expected ISO-8601).")

        if timezone.is_naive(dt):
            # Default to UTC for naive values to avoid accidental local-time interpretations.
            dt = timezone.make_aware(dt, timezone=timezone.utc)
        return dt

    def _parse_uuid_optional(self, value: Optional[str]) -> Optional[uuid.UUID]:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError) as e:
            raise CommandError(f"Invalid UUID value: {value!r}") from e

    def _build_queryset(
        self,
        *,
        before,
        source_id: Optional[uuid.UUID],
        subject_id: Optional[uuid.UUID],
    ) -> QuerySet:
        qs = models.Observation.objects.filter(recorded_at__lt=before)

        if source_id:
            return qs.filter(source_id=source_id)

        if subject_id:
            # Only include observations that belong to the subject at the observation time.
            # This matches ObservationManager.get_subject_observations behavior.
            return qs.filter(
                source__subjectsource__subject_id=subject_id,
                source__subjectsource__assigned_range__contains=F("recorded_at"),
            )

        raise CommandError("Must provide exactly one of --source-id, --source-manufacturer-id, or --subject-id.")

    def _delete_in_batches(self, qs: QuerySet, *, batch_size: int, dry_run: bool) -> int:
        if dry_run:
            # Count distinct observation IDs to avoid double-counting duplicates that arise
            # from the SubjectSource JOIN in the subject-filtered queryset.
            total = qs.values("id").distinct().count()
            for start in range(0, total, batch_size):
                chunk = min(batch_size, total - start)
                self.logger.info(f"Dry run: would delete {chunk} observation(s) in this batch.")
            return total

        # Real delete path: operate on primary keys per batch. This avoids issues with JOIN
        # duplication (e.g. subject filter) and keeps delete statements small.
        total = 0
        while True:
            with transaction.atomic(using=qs.db):
                ids = list(qs.order_by("recorded_at").values_list("id", flat=True)[:batch_size])
                if not ids:
                    break

                # Deduplicate in case the queryset join produces duplicates.
                unique_ids = list(dict.fromkeys(ids))

                models.Observation.objects.filter(id__in=unique_ids)._raw_delete(qs.db)
                total += len(unique_ids)
                self.logger.info(f"Deleted {len(unique_ids)} observation(s) in this batch.")

        return total
