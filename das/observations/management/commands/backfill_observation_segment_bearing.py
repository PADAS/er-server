from django.core.management import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Backfill bearing_deg field for existing ObservationSegments"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10000,
            help="Number of segments to process per batch",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without making changes",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        if dry_run:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM observations_observationsegment WHERE bearing_deg IS NULL"
                )
                remaining = cursor.fetchone()[0]
                self.stdout.write(
                    self.style.WARNING(
                        f"DRY RUN: Would process {remaining} segments with NULL bearing_deg"
                    )
                )
            return

        # Use raw SQL for efficient batch updates with bearing calculation
        # This uses the same great circle formula as the model's compute_bearing_deg method
        sql = """
        UPDATE observations_observationsegment seg
        SET bearing_deg = (
            /* Calculate bearing from start to end using great circle formula */
            /* Returns bearing in degrees [0, 360) */
            (
                DEGREES(
                    ATAN2(
                        SIN(RADIANS(ST_X(end_obs.location) - ST_X(start_obs.location))) * COS(RADIANS(ST_Y(end_obs.location))),
                        COS(RADIANS(ST_Y(start_obs.location))) * SIN(RADIANS(ST_Y(end_obs.location))) -
                        SIN(RADIANS(ST_Y(start_obs.location))) * COS(RADIANS(ST_Y(end_obs.location))) *
                        COS(RADIANS(ST_X(end_obs.location) - ST_X(start_obs.location)))
                    )
                ) + 360
            ) % 360
        )
        FROM observations_observation start_obs, observations_observation end_obs
        WHERE seg.start_observation_id = start_obs.id
          AND seg.end_observation_id = end_obs.id
          AND seg.das_tenant_id = start_obs.das_tenant_id
          AND seg.das_tenant_id = end_obs.das_tenant_id
          AND seg.bearing_deg IS NULL
          AND seg.id IN (
              SELECT id FROM observations_observationsegment
              WHERE bearing_deg IS NULL
              ORDER BY created_at
              LIMIT %s
          )
        """

        with connection.cursor() as cursor:
            total_updated = 0
            iteration = 0

            while True:
                iteration += 1
                self.stdout.write(f"Processing batch {iteration}...")

                cursor.execute(sql, [batch_size])
                updated = cursor.rowcount
                total_updated += updated

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Updated {updated} segments (total: {total_updated})"
                    )
                )

                if updated < batch_size:
                    break

        self.stdout.write(
            self.style.SUCCESS(
                f"\nBackfill complete: {total_updated} segments updated with bearing_deg"
            )
        )
