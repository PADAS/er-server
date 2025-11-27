"""
Management command to backfill ObservationSegments from existing Observations.

This command processes observations in batches and creates segments between
consecutive observations for each subject.

Usage:
    # Backfill all subjects
    python manage.py backfill_observation_segments

    # Backfill specific subjects
    python manage.py backfill_observation_segments --subject-ids uuid1,uuid2,uuid3

    # Backfill with custom batch size
    python manage.py backfill_observation_segments --batch-size 1000

    # Dry run to see what would be processed
    python manage.py backfill_observation_segments --dry-run

    # Process observations from a specific date range
    python manage.py backfill_observation_segments --since 2023-01-01 --until 2023-12-31
"""

import logging
from datetime import datetime
from uuid import UUID

import pytz

from django.core.management.base import BaseCommand
from django.db.models import Count

from observations.models import Observation, ObservationSegment, Subject, SubjectSource
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = "Backfill ObservationSegments from existing Observations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject-ids",
            type=str,
            help="Comma-separated list of subject UUIDs to process (default: all subjects)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of observations to process per batch (default: 500)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Don't actually create segments, just report what would be done",
        )
        parser.add_argument(
            "--since",
            type=str,
            help="Process observations since this date (ISO format: YYYY-MM-DD)",
        )
        parser.add_argument(
            "--until",
            type=str,
            help="Process observations until this date (ISO format: YYYY-MM-DD)",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            default=False,
            help="Clear existing segments before backfilling",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.batch_size = options["batch_size"]

        # Parse date filters
        since = None
        until = None
        if options["since"]:
            since = pytz.utc.localize(datetime.fromisoformat(options["since"]))
        if options["until"]:
            until = pytz.utc.localize(datetime.fromisoformat(options["until"]))

        # Get subjects to process
        if options["subject_ids"]:
            subject_ids = [UUID(s.strip()) for s in options["subject_ids"].split(",")]
            subjects = Subject.objects.filter(id__in=subject_ids)
            self.stdout.write(f"Processing {subjects.count()} specified subjects")
        else:
            # Get all subjects that have observations
            subjects = Subject.objects.annotate(obs_count=Count("subjectsource__source__observation")).filter(
                obs_count__gt=0
            )
            self.stdout.write(f"Processing all {subjects.count()} subjects with observations")

        # Clear existing segments if requested
        if options["clear_existing"] and not self.dry_run:
            self.stdout.write(self.style.WARNING("Clearing existing segments..."))
            deleted_count = ObservationSegment.objects.all().delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} existing segments"))

        # Process each subject
        total_subjects = subjects.count()
        total_segments_created = 0
        subjects_processed = 0

        for subject in subjects.iterator():
            subjects_processed += 1
            self.stdout.write(
                f"\n[{subjects_processed}/{total_subjects}] Processing subject: {subject.name} ({subject.id})"
            )

            segments_created = self.process_subject(subject, since, until)
            total_segments_created += segments_created

        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n{'=' * 80}"))
        self.stdout.write(self.style.SUCCESS("Backfill complete!"))
        self.stdout.write(self.style.SUCCESS(f"Subjects processed: {subjects_processed}"))
        self.stdout.write(self.style.SUCCESS(f"Total segments created: {total_segments_created}"))
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No segments were actually created"))

    def process_subject(self, subject, since=None, until=None):
        """
        Process all observations for a subject and create segments.

        Args:
            subject: Subject instance
            since: Optional datetime to filter observations
            until: Optional datetime to filter observations

        Returns:
            int: Number of segments created
        """
        # Get all sources for this subject
        subject_sources = SubjectSource.objects.filter(subject=subject).values_list("source_id", flat=True)

        if not subject_sources:
            self.stdout.write(self.style.WARNING(f"  No sources found for subject {subject.name}"))
            return 0

        # Build observation queryset
        obs_qs = Observation.objects.filter(source_id__in=subject_sources, location__isnull=False).order_by(
            "recorded_at"
        )

        if since:
            obs_qs = obs_qs.filter(recorded_at__gte=since)
        if until:
            obs_qs = obs_qs.filter(recorded_at__lte=until)

        total_observations = obs_qs.count()
        if total_observations == 0:
            self.stdout.write(f"  No observations found")
            return 0

        if total_observations == 1:
            self.stdout.write(f"  Only 1 observation found, no segments to create")
            return 0

        self.stdout.write(f"  Found {total_observations} observations")

        # Process observations in batches to avoid memory issues
        segments_created = 0
        observations_processed = 0

        # We need to keep track of the previous observation across batches
        prev_obs = None

        # Process in batches
        offset = 0
        while offset < total_observations:
            batch = list(obs_qs[offset : offset + self.batch_size])
            batch_size = len(batch)

            if batch_size == 0:
                break

            # Create segments for this batch
            batch_segments = self.create_segments_for_batch(subject, batch, prev_obs)
            segments_created += batch_segments

            # Update counters
            observations_processed += batch_size
            offset += self.batch_size

            # The last observation of this batch becomes the prev_obs for the next batch
            if batch:
                prev_obs = batch[-1]

            # Progress update
            progress_pct = (observations_processed / total_observations) * 100
            self.stdout.write(
                f"  Progress: {observations_processed}/{total_observations} observations "
                f"({progress_pct:.1f}%) - {segments_created} segments created",
                ending="\r",
            )

        self.stdout.write("")  # New line after progress
        self.stdout.write(self.style.SUCCESS(f"  Created {segments_created} segments"))
        return segments_created

    def create_segments_for_batch(self, subject, observations, prev_obs_from_last_batch=None):
        """
        Create segments for a batch of observations.

        Args:
            subject: Subject instance
            observations: List of Observation instances (ordered by recorded_at)
            prev_obs_from_last_batch: Previous observation from the last batch (if any)

        Returns:
            int: Number of segments created
        """
        if not observations:
            return 0

        segments_created = 0

        # Create segment from last batch's last observation to this batch's first observation
        if prev_obs_from_last_batch:
            first_obs = observations[0]
            if not self.dry_run:
                try:
                    ObservationSegment.objects.create_segment(prev_obs_from_last_batch, first_obs, subject)
                    segments_created += 1
                except Exception as e:
                    logger.error(f"Failed to create segment {prev_obs_from_last_batch.id} -> {first_obs.id}: {e}")
            else:
                segments_created += 1

        # Create segments within this batch
        for i in range(len(observations) - 1):
            start_obs = observations[i]
            end_obs = observations[i + 1]

            if not self.dry_run:
                try:
                    ObservationSegment.objects.create_segment(start_obs, end_obs, subject)
                    segments_created += 1
                except Exception as e:
                    logger.error(f"Failed to create segment {start_obs.id} -> {end_obs.id}: {e}")
            else:
                segments_created += 1

        return segments_created
