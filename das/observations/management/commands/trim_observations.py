import logging
import uuid
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from observations import models
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

        qs = self._build_queryset(
            before=before,
            source_id=source_id,
            source_manufacturer_id=source_manufacturer_id,
            subject_id=subject_id,
        )

        scope = (
            f"source_id={source_id}"
            if source_id
            else (
                f"source_manufacturer_id={source_manufacturer_id!r}"
                if source_manufacturer_id
                else f"subject_id={subject_id}"
            )
        )
        self.logger.info(
            f"Trimming observations where recorded_at < {before.isoformat()} for {scope} (dry_run={dry_run})"
        )

        deleted = self._delete_in_batches(qs, batch_size=batch_size, dry_run=dry_run)
        self.logger.info(f"Done. {'Would delete' if dry_run else 'Deleted'} {deleted} observation(s).")

        if subject_id and not dry_run:
            # Keep SubjectStatus consistent after trimming a subject's observations.
            # Import lazily so running this command doesn't require Celery to be loaded
            # until we actually need to enqueue.
            from observations.tasks import maintain_subjectstatus_for_subject

            maintain_subjectstatus_for_subject.apply_async(args=(str(subject_id),))
            self.logger.info(f"Queued maintain_subjectstatus_for_subject for subject_id={subject_id}")

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
        source_manufacturer_id: Optional[str],
        subject_id: Optional[uuid.UUID],
    ) -> QuerySet:
        qs = models.Observation.objects.filter(recorded_at__lt=before)

        if source_id:
            return qs.filter(source_id=source_id)

        if source_manufacturer_id:
            sources = models.Source.objects.filter(manufacturer_id=source_manufacturer_id)
            if not sources.exists():
                self.logger.info(f"No Source found with manufacturer_id={source_manufacturer_id!r}. Nothing to do.")
                return qs.none()
            if sources.count() > 1:
                raise CommandError(f"Source manufacturer_id={source_manufacturer_id!r} is not unique for this tenant.")
            return qs.filter(source_id=sources.first().id)

        if subject_id:
            # Only include observations that belong to the subject at the observation time.
            # This matches ObservationManager.get_subject_observations behavior.
            return qs.filter(
                source__subjectsource__subject_id=subject_id,
                source__subjectsource__assigned_range__contains=F("recorded_at"),
            )

        raise CommandError("Must provide exactly one of --source-id, --source-manufacturer-id, or --subject-id.")

    def _delete_in_batches(self, qs: QuerySet, *, batch_size: int, dry_run: bool) -> int:
        total = 0

        # Note: We purposely operate on primary keys per batch. This avoids issues with JOIN
        # duplication (e.g. subject filter) and keeps delete statements small.
        while True:
            with transaction.atomic(using=qs.db):
                ids = list(qs.order_by("recorded_at").values_list("id", flat=True)[:batch_size])
                if not ids:
                    break

                # Deduplicate in case the queryset join produces duplicates.
                unique_ids = list(dict.fromkeys(ids))

                if dry_run:
                    total += len(unique_ids)
                    self.logger.info(f"Dry run: would delete {len(unique_ids)} observation(s) in this batch.")
                    # Remove the already-counted IDs from consideration for next loop.
                    qs = qs.exclude(id__in=unique_ids)
                    continue

                models.Observation.objects.filter(id__in=unique_ids)._raw_delete(qs.db)
                total += len(unique_ids)
                self.logger.info(f"Deleted {len(unique_ids)} observation(s) in this batch.")

        return total
