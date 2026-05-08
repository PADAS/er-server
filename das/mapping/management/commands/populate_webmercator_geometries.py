import logging
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from mapping.models import SpatialFeature
from utils.cache import bump_vector_tile_data_version
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = "Populate feature_geometry_webmercator field for existing SpatialFeatures in batches"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=1000, help="Number of records to process per batch (default: 1000)"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be processed without making changes"
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]
        queryset = self._build_queryset()
        total_count = queryset.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No SpatialFeatures need Web Mercator geometry processing."))
            return

        self._print_initial_status(total_count, dry_run)
        processed, failed = self._process_batches(queryset, batch_size, dry_run, total_count)
        self._print_final_summary(processed, failed)

        # Bump vector tile cache version if we processed any features
        if not dry_run:
            bump_vector_tile_data_version()
            self.stdout.write(self.style.SUCCESS("Vector tile cache version bumped."))

    def _build_queryset(self):
        """Build the queryset of features that need processing."""
        return SpatialFeature.objects.filter(
            feature_geometry__isnull=False, feature_geometry_webmercator__isnull=True
        ).order_by("id")

    def _print_initial_status(self, total_count, dry_run):
        """Print initial processing status."""
        self.stdout.write(f"Found {total_count} SpatialFeatures to process")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

    def _process_batches(self, queryset, batch_size, dry_run, total_count):
        """Process features in batches and return (processed_count, failed_count)."""
        processed = 0
        failed = 0
        batch_num = 0
        processed_ids = set()

        while True:
            batch_num += 1
            # Get next batch, excluding already processed IDs
            current_queryset = queryset.exclude(id__in=processed_ids) if processed_ids else queryset
            batch = list(current_queryset[:batch_size])

            if not batch:
                break

            batch_processed, batch_failed = self._process_single_batch(batch, dry_run, batch_num)

            processed += batch_processed
            failed += batch_failed

            # Track processed IDs for exclusion in next batch
            processed_ids.update(feature.id for feature in batch)

            self._print_progress(processed, failed, total_count)

        return processed, failed

    def _process_single_batch(self, batch, dry_run, batch_num):
        """Process a single batch and return (processed_count, failed_count)."""
        batch_start_time = datetime.now(tz=timezone.utc)
        batch_processed = 0
        batch_failed = 0

        if not dry_run:
            # Process all features in batch, collect successful updates
            features_to_update = []

            for feature in batch:
                try:
                    webmerc_geom = feature._generate_webmercator_geometry()
                    if webmerc_geom:
                        feature.feature_geometry_webmercator = webmerc_geom
                        features_to_update.append(feature)
                        batch_processed += 1
                    else:
                        logger.error("Failed to generate geometry for SpatialFeature %s", feature.id)
                        batch_failed += 1
                except Exception as e:
                    logger.exception("Error processing SpatialFeature %s: %s", feature.id, e)
                    batch_failed += 1

            # Bulk update all successful geometries in one transaction
            if features_to_update:
                self._bulk_update_geometries(features_to_update)
        else:
            # Dry run - just count what we would process
            batch_processed = len(batch)

        batch_duration = datetime.now(tz=timezone.utc) - batch_start_time
        rate = batch_processed / batch_duration.total_seconds() if batch_duration.total_seconds() > 0 else 0

        self.stdout.write(
            f"Batch {batch_num}: Processed {batch_processed}, "
            f"Failed {batch_failed}, "
            f"Duration: {batch_duration.total_seconds():.2f}s, "
            f"Rate: {rate:.1f} features/sec"
        )

        return batch_processed, batch_failed

    def _bulk_update_geometries(self, features_to_update):
        """Bulk update geometries using Django's bulk_update for better performance."""
        if not features_to_update:
            return

        # Bulk update in a single query
        with transaction.atomic():
            SpatialFeature.objects.bulk_update(features_to_update, ["feature_geometry_webmercator", "updated_at"])

    def _print_progress(self, processed, failed, total_count):
        """Print current progress status."""
        percentage = (processed / total_count) * 100 if total_count > 0 else 0
        self.stdout.write(f"Progress: {processed}/{total_count} ({percentage:.1f}%) processed, {failed} failed")

    def _print_final_summary(self, processed, failed):
        """Print final processing summary."""
        self.stdout.write(self.style.SUCCESS(f"Completed! Processed: {processed}, Failed: {failed}"))

        if failed > 0:
            self.stdout.write(self.style.WARNING(f"{failed} features failed processing. Check logs for details."))
