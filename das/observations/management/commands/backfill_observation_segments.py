"""
Management command to backfill ObservationSegments using the same interface as the async task.

Invokes recompute_observation_segments_for_source_range (sync) or enqueues
recompute_observation_segments_task (async) per SubjectSource, so there is a single
code path for segment recompute regardless of trigger (SubjectSource signal vs backfill).

Usage:
    # Backfill current tenant (sync)
    python manage.py backfill_observation_segments --tenant_domain zoo.com

    # Enqueue async tasks per SubjectSource instead of running in-process
    python manage.py backfill_observation_segments --tenant_domain zoo.com --async

    # Dry run to see what would be processed
    python manage.py backfill_observation_segments --tenant_domain zoo.com --dry-run
"""

import logging

from django.core.management.base import BaseCommand

from observations.models import SubjectSource
from observations.signals import recompute_observation_segments_for_source_range
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = "Backfill ObservationSegments via the common recompute interface (sync or async)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Don't run recompute, just report what would be done",
        )
        parser.add_argument(
            "--async",
            dest="async_",
            action="store_true",
            default=False,
            help="Enqueue one Celery task per SubjectSource instead of running recompute in-process",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        async_ = options["async_"]

        # SubjectSource is tenant-scoped; we're in tenant context from TenantCommandMixin
        subject_sources = SubjectSource.objects.select_related("source").all()
        total = subject_sources.count()
        self.stdout.write(f"SubjectSources to process: {total}")

        if total == 0:
            self.stdout.write(self.style.WARNING("No SubjectSource records found for this tenant."))
            return

        if dry_run:
            for i, ss in enumerate(subject_sources.iterator(), 1):
                self.stdout.write(
                    f"  [{i}/{total}] source={ss.source_id} range={ss.assigned_range.lower} .. {ss.assigned_range.upper}"
                )
            self.stdout.write(self.style.WARNING("DRY RUN - No recompute was performed."))
            return

        domain = get_tenant_settings().domain
        processed = 0
        for ss in subject_sources.iterator():
            processed += 1
            lower, upper = ss.assigned_range.lower, ss.assigned_range.upper
            if async_:
                from observations.tasks import recompute_observation_segments_task

                recompute_observation_segments_task.apply_async(
                    kwargs={
                        "source_id": str(ss.source_id),
                        "lower": lower,
                        "upper": upper,
                        "domain": domain,
                    }
                )
                self.stdout.write(
                    f"  [{processed}/{total}] Enqueued task for source={ss.source_id}",
                    ending="\r",
                )
            else:
                recompute_observation_segments_for_source_range(ss.source_id, lower, upper)
                self.stdout.write(
                    f"  [{processed}/{total}] Recomputed segments for source={ss.source_id}",
                    ending="\r",
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Processed {processed} SubjectSource(s)."))
        if async_:
            self.stdout.write(self.style.SUCCESS("Tasks were enqueued; workers will run recompute."))
