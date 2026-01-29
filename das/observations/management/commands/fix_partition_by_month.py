"""
Django management command to fix a specific monthly partition by moving data
from the default partition.

This command uses a staging table approach designed for online systems:
1. Creates a temporary staging table
2. LOOPS to move data for the target month from default → staging (handles concurrent inserts)
3. Uses pg_partman's partition_data_time() to create the partition and move staged data
4. Cleans up the staging table

The loop in step 2 ensures that observations arriving during the process are captured.
It will continue moving data from default to staging until no more rows for that month
are found in the default partition.

More information: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_time

Examples:
    # Fix January 2024 partition
    python manage.py fix_partition_by_month --year 2024 --month 1

    # Fix with custom batch processing
    python manage.py fix_partition_by_month -y 2024 -m 3 --batch-count 10

    # Preview what would happen without making changes
    python manage.py fix_partition_by_month -y 2024 -m 6 --dry-run
"""

import logging

from psycopg2 import sql as psycopg2_sql

from django.core.management import BaseCommand
from django.core.management.base import CommandError

from utils.db.postgresql import (
    FetchType,
    PSQLExtension,
    begin,
    commit,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_partition_data_time_query,
    rollback,
    safe_table_reference,
    to_fully_qualified_table_name,
    vacuum_analyze_query,
)


class Command(BaseCommand):
    help = """Fix a missing monthly partition by moving data from the default partition.
    Uses a staging table to safely move data for a specific month. Supports pg_partman 5.2.4+."""

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            type=str,
            help="PostgreSQL schema to select",
            default="public",
        )
        parser.add_argument(
            "-t",
            "--table",
            type=str,
            help="PostgreSQL table",
            default="observations_observation",
        )
        parser.add_argument(
            "-y",
            "--year",
            type=int,
            help="Year of the partition to fix (e.g., 2024)",
            required=True,
        )
        parser.add_argument(
            "-m",
            "--month",
            type=int,
            help="Month of the partition to fix (1-12)",
            required=True,
        )
        parser.add_argument(
            "--batch-count",
            type=int,
            help="Number of times to run the batch when moving from staging. If not specified, runs until completion.",
            default=None,
        )
        parser.add_argument(
            "--batch-interval",
            type=str,
            help="Interval of time to process per batch (e.g., '1 week'). If not specified, uses partition interval.",
            default=None,
        )
        parser.add_argument(
            "--lock-wait",
            type=float,
            help="Amount of time in seconds to wait for locks. If not specified, waits indefinitely.",
            default=None,
        )
        parser.add_argument(
            "-o",
            "--order",
            type=str,
            choices=["ASC", "DESC"],
            help="Order to process data: ASC or DESC (default: ASC)",
            default="ASC",
        )
        parser.add_argument(
            "--no-analyze",
            action="store_true",
            help="Skip ANALYZE after moving data",
            default=False,
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview what would happen without making any changes (read-only)",
        )

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)

        logger.info(f"options: {options}")
        schema = options["schema"]
        table_name = options["table"]
        year = options["year"]
        month = options["month"]
        batch_count = options["batch_count"]
        batch_interval = options["batch_interval"]
        lock_wait = options["lock_wait"]
        order = options["order"]
        analyze = not options["no_analyze"]
        is_dry_run = options["dry_run"]

        # Validate month
        if not (1 <= month <= 12):
            self.stdout.write(self.style.ERROR("Month must be between 1 and 12."))
            return

        # Check pg_partman
        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            self.stdout.write(self.style.WARNING("pg_partman is not installed, skipping..."))
            return

        logger.info("pg_partman is properly installed.")

        # Calculate date range for the target month
        # Handle year boundary for upper bound
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year = year + 1

        start_date = f"{year:04d}-{month:02d}-01 00:00:00+00"
        end_date = f"{next_year:04d}-{next_month:02d}-01 00:00:00+00"

        # Define table names
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
        default_table = f"{fully_qualified_table}_default"
        staging_table_name = f"{table_name}_stage_{year:04d}_{month:02d}"
        staging_table = to_fully_qualified_table_name(schema=schema, table_name=staging_table_name)

        # Dry-run mode: preview only, no changes made
        if is_dry_run:
            self._handle_dry_run(
                logger=logger,
                schema=schema,
                table_name=table_name,
                year=year,
                month=month,
                start_date=start_date,
                end_date=end_date,
                fully_qualified_table=fully_qualified_table,
                default_table=default_table,
                staging_table_name=staging_table_name,
                staging_table=staging_table,
                batch_count=batch_count,
                batch_interval=batch_interval,
                lock_wait=lock_wait,
                order=order,
                analyze=analyze,
            )
            return

        # Normal execution mode
        self._handle_execution(
            logger=logger,
            schema=schema,
            table_name=table_name,
            year=year,
            month=month,
            start_date=start_date,
            end_date=end_date,
            fully_qualified_table=fully_qualified_table,
            default_table=default_table,
            staging_table_name=staging_table_name,
            staging_table=staging_table,
            batch_count=batch_count,
            batch_interval=batch_interval,
            lock_wait=lock_wait,
            order=order,
            analyze=analyze,
        )

    def _handle_dry_run(
        self,
        logger,
        schema: str,
        table_name: str,
        year: int,
        month: int,
        start_date: str,
        end_date: str,
        fully_qualified_table: str,
        default_table: str,
        staging_table_name: str,
        staging_table: str,
        batch_count: int | None,
        batch_interval: str | None,
        lock_wait: float | None,
        order: str,
        analyze: bool,
    ):
        """Preview what would happen without making any changes."""
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(f"Target partition: {year:04d}-{month:02d}"))
        self.stdout.write(f"  Date range: {start_date} to {end_date}")
        self.stdout.write(f"  Parent table: {fully_qualified_table}")
        self.stdout.write(f"  Default partition: {default_table}")
        self.stdout.write(f"  Staging table (to be created): {staging_table}")
        self.stdout.write("")

        # Check if staging table already exists
        check_staging_sql = """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s;
        """
        staging_exists = execute_sql_query(
            query=check_staging_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, staging_table_name)
        )

        if staging_exists and staging_exists[0] > 0:
            self.stdout.write(
                self.style.ERROR(f"ERROR: Staging table {staging_table} already exists. Command would fail.")
            )
            return

        self.stdout.write(self.style.SUCCESS("Staging table does not exist (OK)"))

        # Check if target partition already exists
        expected_partition_name = f"{table_name}_p{year:04d}_{month:02d}"
        check_partition_sql = """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s;
        """
        partition_exists = execute_sql_query(
            query=check_partition_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, expected_partition_name)
        )

        if partition_exists and partition_exists[0] > 0:
            self.stdout.write(self.style.WARNING(f"Note: Target partition {expected_partition_name} already exists"))
        else:
            self.stdout.write(f"Target partition {expected_partition_name} will be created")

        # Count rows in default partition for target month
        # Use psycopg2.sql for safe identifier composition
        default_table_ref = safe_table_reference(schema, f"{table_name}_default")
        count_default_sql = psycopg2_sql.SQL(
            """
            SELECT COUNT(*)
            FROM ONLY {table}
            WHERE recorded_at >= %s::timestamptz
              AND recorded_at < %s::timestamptz;
        """
        ).format(table=default_table_ref)
        count_result = execute_sql_query(
            query=count_default_sql, logger=logger, fetch_type=FetchType.ONE, params=(start_date, end_date)
        )
        rows_to_move = count_result[0] if count_result else 0

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Data Analysis:"))
        self.stdout.write(f"  Rows in default partition for {year:04d}-{month:02d}: {rows_to_move:,}")

        if rows_to_move == 0:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("No data found in default partition for this month."))
            self.stdout.write(self.style.WARNING("Running this command would have no effect."))
            return

        # Show date range of affected data
        date_range_sql = psycopg2_sql.SQL(
            """
            SELECT MIN(recorded_at), MAX(recorded_at)
            FROM ONLY {table}
            WHERE recorded_at >= %s::timestamptz
              AND recorded_at < %s::timestamptz;
        """
        ).format(table=default_table_ref)
        date_range = execute_sql_query(
            query=date_range_sql, logger=logger, fetch_type=FetchType.ONE, params=(start_date, end_date)
        )
        if date_range and date_range[0]:
            self.stdout.write(f"  Earliest record: {date_range[0]}")
            self.stdout.write(f"  Latest record: {date_range[1]}")

        # Show planned operations
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Planned Operations:"))
        self.stdout.write(f"  1. Create staging table: {staging_table}")
        self.stdout.write(f"  2. Move ~{rows_to_move:,} rows from {default_table} to {staging_table}")
        self.stdout.write(f"  3. Run partition_data_time() to create partition and move data from staging")
        self.stdout.write(f"  4. Drop staging table: {staging_table}")
        if analyze:
            self.stdout.write(f"  5. Run VACUUM ANALYZE on {fully_qualified_table}")

        # Show partition_data_time parameters
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("partition_data_time() parameters:"))
        self.stdout.write(f"  p_parent_table: {fully_qualified_table}")
        self.stdout.write(f"  p_source_table: {staging_table}")
        self.stdout.write(f"  p_batch_count: {batch_count or 'default'}")
        self.stdout.write(f"  p_batch_interval: {batch_interval or 'default (partition interval)'}")
        self.stdout.write(f"  p_lock_wait: {lock_wait or 'default (wait indefinitely)'}")
        self.stdout.write(f"  p_order: {order}")
        self.stdout.write(f"  p_analyze: {analyze}")

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("To execute these changes, run without --dry-run"))
        self.stdout.write(self.style.WARNING("=" * 60))

    def _handle_execution(
        self,
        logger,
        schema: str,
        table_name: str,
        year: int,
        month: int,
        start_date: str,
        end_date: str,
        fully_qualified_table: str,
        default_table: str,
        staging_table_name: str,
        staging_table: str,
        batch_count: int | None,
        batch_interval: str | None,
        lock_wait: float | None,
        order: str,
        analyze: bool,
    ):
        """Execute the partition fix operation."""
        self.stdout.write(
            self.style.SUCCESS(f"Fixing partition for {year:04d}-{month:02d} (data range: {start_date} to {end_date})")
        )
        logger.info(f"Target date range: {start_date} to {end_date}")
        logger.info(f"Staging table: {staging_table}")

        try:
            # Step 1: Create staging table
            begin(logger=logger)

            # Check if staging table already exists
            check_staging_sql = """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s;
            """
            staging_exists = execute_sql_query(
                query=check_staging_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, staging_table_name)
            )

            if staging_exists and staging_exists[0] > 0:
                self.stdout.write(self.style.WARNING(f"Staging table {staging_table} already exists. Exiting..."))
                rollback(logger=logger)
                raise CommandError(f"Staging table {staging_table} already exists.")

            # Create staging table using safe identifier composition
            self.stdout.write(self.style.SUCCESS(f"Creating staging table: {staging_table}"))
            staging_table_ref = safe_table_reference(schema, staging_table_name)
            parent_table_ref = safe_table_reference(schema, table_name)
            create_staging_sql = psycopg2_sql.SQL(
                """
                CREATE TABLE {staging_table}
                (LIKE {parent_table} INCLUDING ALL);
            """
            ).format(staging_table=staging_table_ref, parent_table=parent_table_ref)
            execute_sql_query(query=create_staging_sql, logger=logger, fetch_type=FetchType.NONE)
            logger.info(f"Created staging table: {staging_table}")

            # Set REPLICA IDENTITY FULL on staging table to support logical replication
            # This is required when the database has publications that include deletes
            set_replica_identity_sql = psycopg2_sql.SQL("ALTER TABLE {staging_table} REPLICA IDENTITY FULL;").format(
                staging_table=staging_table_ref
            )
            execute_sql_query(query=set_replica_identity_sql, logger=logger, fetch_type=FetchType.NONE)
            logger.info(f"Set REPLICA IDENTITY FULL on staging table: {staging_table}")

            commit(logger=logger)
            self.stdout.write(self.style.SUCCESS("Staging table created"))

            # Step 2: Loop to handle ongoing insertions into default
            # Keep moving data from default to staging until no more rows appear
            total_rows_moved_to_staging = 0
            move_iteration = 0
            max_move_iterations = 100  # Safety limit

            # Prepare SQL queries with safe identifiers outside the loop
            default_table_ref = safe_table_reference(schema, f"{table_name}_default")
            count_default_sql = psycopg2_sql.SQL(
                """
                SELECT COUNT(*)
                FROM ONLY {table}
                WHERE recorded_at >= %s::timestamptz
                  AND recorded_at < %s::timestamptz;
            """
            ).format(table=default_table_ref)

            drop_staging_sql = psycopg2_sql.SQL("DROP TABLE {staging_table};").format(staging_table=staging_table_ref)

            while move_iteration < max_move_iterations:
                move_iteration += 1

                # Count rows in default for this month
                count_result = execute_sql_query(
                    query=count_default_sql, logger=logger, fetch_type=FetchType.ONE, params=(start_date, end_date)
                )
                rows_to_move = count_result[0] if count_result else 0

                if rows_to_move == 0:
                    if move_iteration == 1:
                        self.stdout.write(
                            self.style.WARNING(
                                f"No data found in default partition for {year:04d}-{month:02d}. Nothing to do."
                            )
                        )
                        # Clean up empty staging table
                        execute_sql_query(query=drop_staging_sql, logger=logger, fetch_type=FetchType.NONE)
                        return
                    else:
                        # No more rows found after previous iterations
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"No more rows in default partition after {move_iteration - 1} iteration(s)"
                            )
                        )
                        break

                logger.info(f"Move iteration {move_iteration}: Found {rows_to_move} rows in default")
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Iteration {move_iteration}: Moving {rows_to_move} rows from default to staging..."
                    )
                )

                # Atomically move data from default to staging
                begin(logger=logger)
                move_sql = psycopg2_sql.SQL(
                    """
                    WITH moved_rows AS (
                        DELETE FROM ONLY {default_table}
                        WHERE recorded_at >= %s::timestamptz
                          AND recorded_at < %s::timestamptz
                        RETURNING *
                    )
                    INSERT INTO {staging_table}
                    SELECT * FROM moved_rows;
                """
                ).format(default_table=default_table_ref, staging_table=staging_table_ref)
                execute_sql_query(
                    query=move_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date)
                )
                commit(logger=logger)

                total_rows_moved_to_staging += rows_to_move
                logger.info(f"Moved {rows_to_move} rows (total: {total_rows_moved_to_staging})")

            if move_iteration >= max_move_iterations:
                raise Exception(
                    f"Exceeded maximum move iterations ({max_move_iterations}). "
                    f"Data is still being inserted into default partition. Consider running during low traffic period."
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully moved {total_rows_moved_to_staging} rows to staging across {move_iteration} iteration(s)"
                )
            )

            # Step 3: Use pg_partman to create partition and move data from staging
            self.stdout.write(self.style.SUCCESS("Running partition_data_time to create partition and move data..."))

            partition_sql = partman_partition_data_time_query(
                schema=schema,
                table_name=table_name,
                p_batch_count=batch_count,
                p_batch_interval=batch_interval,
                p_lock_wait=lock_wait,
                p_order=order,
                p_analyze=analyze,
                p_source_table=staging_table,
            )

            logger.info(f'Executing: "{partition_sql}"')

            # Run partition_data_time until it returns 0 (all data moved)
            total_moved = 0
            iteration = 0
            while True:
                iteration += 1
                result = execute_sql_query(query=partition_sql, logger=logger, fetch_type=FetchType.ONE)
                moved = result[0] if result else 0
                total_moved += moved

                logger.info(f"Iteration {iteration}: Moved {moved} rows (total: {total_moved})")

                if moved == 0:
                    self.stdout.write(self.style.SUCCESS(f"Completed! Total rows moved: {total_moved}"))
                    break

                if iteration > 1000:  # Safety limit
                    raise Exception("Too many iterations (>1000). Possible infinite loop.")

            # Verify staging table is empty
            count_staging_sql = psycopg2_sql.SQL("SELECT COUNT(*) FROM {staging_table};").format(
                staging_table=staging_table_ref
            )
            staging_count = execute_sql_query(query=count_staging_sql, logger=logger, fetch_type=FetchType.ONE)
            remaining = staging_count[0] if staging_count else 0

            if remaining > 0:
                self.stdout.write(
                    self.style.WARNING(f"Warning: {remaining} rows remain in staging table. Check for issues.")
                )
                logger.warning(f"Staging table still has {remaining} rows")
            else:
                self.stdout.write(self.style.SUCCESS("Staging table is empty - all data moved successfully"))

            # Step 4: Clean up staging table
            self.stdout.write(self.style.SUCCESS(f"Dropping staging table: {staging_table}"))
            execute_sql_query(query=drop_staging_sql, logger=logger, fetch_type=FetchType.NONE)
            logger.info(f"Dropped staging table: {staging_table}")

            # Vacuum analyze if enabled
            if analyze:
                self.stdout.write(self.style.SUCCESS("Running VACUUM ANALYZE..."))
                vacuum_sql = vacuum_analyze_query(schema=schema, table_name=table_name)
                execute_sql_query(query=vacuum_sql, logger=logger, fetch_type=FetchType.NONE)
                logger.info("VACUUM ANALYZE completed")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully fixed partition for {year:04d}-{month:02d}. Moved {total_moved} rows."
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fixing partition: {e}"))
            logger.exception("Failed to fix partition")
            try:
                rollback(logger=logger)
                self.stdout.write(self.style.WARNING("Rolled back transaction"))
            except Exception:
                logger.exception("Failed to rollback transaction after error fixing partition")
            raise
