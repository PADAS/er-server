"""
Management command to backfill ObservationSegments in bulk.

Uses a single SQL INSERT … SELECT per distinct subject.  The CTE gathers
every observation for the subject across all sources (each respecting its
own assigned_range) and pairs consecutive observations using LEAD().  This
matches the unbounded cross-source ordering used by
Observation.get_neighbor_observations in the signal path, so boundary
segments between adjacent SubjectSource assignments are never missed.

The outer loop iterates distinct subjects (derived from SubjectSource);
ON CONFLICT … DO NOTHING keeps the operation idempotent.

Usage:
    # Backfill current tenant (sync)
    python manage.py backfill_observation_segments --tenant_domain zoo.com

    # Enqueue async tasks per SubjectSource instead of running in-process
    python manage.py backfill_observation_segments --tenant_domain zoo.com --async

    # Dry run to see what would be processed
    python manage.py backfill_observation_segments --tenant_domain zoo.com --dry-run
"""

import logging

from django_multitenant.utils import get_current_tenant

from django.core.management.base import BaseCommand
from django.db import connection

from observations.models import Subject, SubjectSource
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)

BULK_INSERT_SEGMENTS_SQL = """
WITH subject_obs AS (
    SELECT DISTINCT o.id, o.location, o.recorded_at, o.exclusion_flags, o.das_tenant_id
    FROM observations_observation o
    JOIN observations_subjectsource ss
      ON ss.source_id = o.source_id
     AND ss.das_tenant_id = o.das_tenant_id
     AND o.recorded_at <@ ss.assigned_range
    WHERE ss.subject_id = %(subject_id)s
      AND ss.das_tenant_id = %(tenant_id)s
      AND o.location IS NOT NULL
),
pairs AS (
    SELECT
        id, location, recorded_at, exclusion_flags, das_tenant_id,
        LEAD(id)              OVER w AS next_id,
        LEAD(location)        OVER w AS next_location,
        LEAD(recorded_at)     OVER w AS next_recorded_at,
        LEAD(exclusion_flags) OVER w AS next_exclusion_flags
    FROM subject_obs
    WINDOW w AS (ORDER BY recorded_at)
)
INSERT INTO observations_observationsegment (
    id, geometry, speed_kmh, time_gap_ms, distance_meters, bearing_deg,
    start_recorded_at, end_recorded_at, exclusion_flags,
    created_at, updated_at,
    das_tenant_id, start_observation_id, end_observation_id, subject_id
)
SELECT
    gen_random_uuid(),
    ST_MakeLine(location, next_location),
    CASE WHEN EXTRACT(EPOCH FROM next_recorded_at - recorded_at) > 0
         THEN (ST_Distance(location::geography, next_location::geography) / 1000.0)
              / (EXTRACT(EPOCH FROM next_recorded_at - recorded_at) / 3600.0)
         ELSE 0.0
    END,
    EXTRACT(EPOCH FROM next_recorded_at - recorded_at) * 1000.0,
    ST_Distance(location::geography, next_location::geography),
    MOD(
        DEGREES(ATAN2(
            SIN(RADIANS(ST_X(next_location) - ST_X(location)))
                * COS(RADIANS(ST_Y(next_location))),
            COS(RADIANS(ST_Y(location))) * SIN(RADIANS(ST_Y(next_location)))
              - SIN(RADIANS(ST_Y(location))) * COS(RADIANS(ST_Y(next_location)))
                * COS(RADIANS(ST_X(next_location) - ST_X(location)))
        )) + 360.0,
        360.0
    ),
    recorded_at,
    next_recorded_at,
    exclusion_flags | next_exclusion_flags,
    NOW(),
    NOW(),
    das_tenant_id,
    id,
    next_id,
    %(subject_id)s
FROM pairs
WHERE next_id IS NOT NULL
ON CONFLICT ON CONSTRAINT observations_observationsegment_unique_segment DO NOTHING;
"""


class Command(TenantCommandMixin, BaseCommand):
    help = "Backfill ObservationSegments in bulk using SQL INSERT … SELECT"

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

        subject_sources = SubjectSource.objects.select_related("source", "subject").all()

        if dry_run:
            total = subject_sources.count()
            self.stdout.write(f"SubjectSources found: {total}")
            for i, ss in enumerate(subject_sources.iterator(), 1):
                self.stdout.write(
                    f"  [{i}/{total}] source={ss.source_id} "
                    f"subject={ss.subject_id} "
                    f"range={ss.assigned_range.lower} .. {ss.assigned_range.upper}"
                )
            self.stdout.write(self.style.WARNING("DRY RUN - No recompute was performed."))
            return

        if async_:
            self._handle_async(subject_sources)
        else:
            subjects = Subject.objects.filter(subjectsources__isnull=False).distinct()
            self._handle_sync(subjects)

    def _handle_sync(self, subjects):
        tenant_id = get_current_tenant().id
        total = subjects.count()
        self.stdout.write(f"Subjects to process: {total}")

        if total == 0:
            self.stdout.write(self.style.WARNING("No subjects with source assignments found."))
            return

        total_created = 0
        for i, subj in enumerate(subjects.iterator(), 1):
            with connection.cursor() as cursor:
                cursor.execute(
                    BULK_INSERT_SEGMENTS_SQL,
                    {
                        "subject_id": subj.id,
                        "tenant_id": tenant_id,
                    },
                )
                created = cursor.rowcount
            total_created += created
            self.stdout.write(f"  [{i}/{total}] subject={subj.name!r} segments_created={created}")

        self.stdout.write(self.style.SUCCESS(f"Done. Processed {total} subject(s), created {total_created} segments."))

    def _handle_async(self, subject_sources):
        from observations.tasks import recompute_observation_segments_task

        total = subject_sources.count()
        self.stdout.write(f"SubjectSources to enqueue: {total}")

        if total == 0:
            self.stdout.write(self.style.WARNING("No SubjectSource records found for this tenant."))
            return

        domain = get_tenant_settings().domain
        for i, ss in enumerate(subject_sources.iterator(), 1):
            lower, upper = ss.assigned_range.lower, ss.assigned_range.upper
            recompute_observation_segments_task.apply_async(
                kwargs={
                    "source_id": str(ss.source_id),
                    "lower": lower,
                    "upper": upper,
                    "domain": domain,
                }
            )
            self.stdout.write(f"  [{i}/{total}] Enqueued task for source={ss.source_id}")

        self.stdout.write(self.style.SUCCESS(f"Done. Enqueued {total} tasks; workers will run recompute."))
