"""
Django management command to fix a specific monthly partition by moving data
from the default partition.

This command uses a direct partition creation approach designed for large datasets
with minimal locking:

1. Creates an unattached partition table (no lock on parent)
2. LOOPS to move data from default → partition (no lock on parent)
3. Adds CHECK constraint to new partition (validates data matches bounds)
4. LOCKS table briefly, then in single transaction:
   - Moves final rows (catches any that arrived during steps 1-3)
   - Adds exclusion CHECK to default (tells PG no conflicting rows exist)
   - Attaches partition (instant - no validation scan needed)
   - Drops the temporary exclusion CHECK
   - Commits (releases lock)

The exclusion CHECK on default is added INSIDE the lock to prevent race conditions
where new data arrives between adding the check and the attach.

Examples:
    # Fix January 2024 partition
    python manage.py fix_partition_by_month --year 2024 --month 1

    # Preview what would happen without making changes
    python manage.py fix_partition_by_month -y 2024 -m 6 --dry-run

    # Resume a previously failed run (when unattached partition exists with data)
    python manage.py fix_partition_by_month -y 2024 -m 10 --resume
"""

import logging

from psycopg2 import sql as psycopg2_sql

from django.core.management import BaseCommand
from django.core.management.base import CommandError

from utils.db.postgresql import (
    FetchType,
    begin,
    commit,
    execute_sql_query,
    rollback,
    safe_table_reference,
    to_fully_qualified_table_name,
    vacuum_analyze_query,
)


class Command(BaseCommand):
    help = """Fix a missing monthly partition by moving data from the default partition.
    Uses direct partition creation with minimal locking for large datasets."""

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
        parser.add_argument(
            "--resume",
            action="store_true",
            default=False,
            help="Resume from a previously failed run. Expects unattached partition to exist.",
        )

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)

        logger.info(f"options: {options}")
        schema = options["schema"]
        table_name = options["table"]
        year = options["year"]
        month = options["month"]
        analyze = not options["no_analyze"]
        is_dry_run = options["dry_run"]
        is_resume = options["resume"]

        # Validate month
        if not (1 <= month <= 12):
            self.stdout.write(self.style.ERROR("Month must be between 1 and 12."))
            return

        # Calculate date range for the target month
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year = year + 1

        start_date = f"{year:04d}-{month:02d}-01 00:00:00+00"
        end_date = f"{next_year:04d}-{next_month:02d}-01 00:00:00+00"

        # Define table names
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
        partition_name = f"{table_name}_p{year:04d}_{month:02d}"
        partition_table = to_fully_qualified_table_name(schema=schema, table_name=partition_name)

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
                partition_name=partition_name,
                partition_table=partition_table,
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
            partition_name=partition_name,
            partition_table=partition_table,
            analyze=analyze,
            resume=is_resume,
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
        partition_name: str,
        partition_table: str,
    ):
        """Preview what would happen without making any changes."""
        default_table = f"{fully_qualified_table}_default"

        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(f"Target partition: {year:04d}-{month:02d}"))
        self.stdout.write(f"  Date range: {start_date} to {end_date}")
        self.stdout.write(f"  Parent table: {fully_qualified_table}")
        self.stdout.write(f"  Default partition: {default_table}")
        self.stdout.write(f"  Target partition: {partition_table}")
        self.stdout.write("")

        # Check if partition already exists
        check_partition_sql = """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s;
        """
        partition_exists = execute_sql_query(
            query=check_partition_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, partition_name)
        )

        if partition_exists and partition_exists[0] > 0:
            # Check if attached
            check_attached_sql = """
                SELECT COUNT(*)
                FROM pg_inherits i
                JOIN pg_class c ON i.inhrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = %s AND c.relname = %s;
            """
            is_attached = execute_sql_query(
                query=check_attached_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, partition_name)
            )
            if is_attached and is_attached[0] > 0:
                self.stdout.write(self.style.WARNING(f"Partition {partition_table} already exists and is attached."))
                self.stdout.write(self.style.WARNING("Running this command would only move any remaining data."))
            else:
                self.stdout.write(
                    self.style.WARNING(f"Partition {partition_table} exists but is NOT attached (use --resume).")
                )
        else:
            self.stdout.write(f"Partition {partition_table} will be created")

        # Count rows in default partition for target month
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
        self.stdout.write(f"  1. Create unattached partition: {partition_table}")
        self.stdout.write(f"  2. Move ~{rows_to_move:,} rows from default → partition (no lock on parent)")
        self.stdout.write(f"  3. Add CHECK constraint (allows fast attach)")
        self.stdout.write(f"  4. ATTACH partition (brief lock, no data scan)")

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
        partition_name: str,
        partition_table: str,
        analyze: bool,
        resume: bool = False,
    ):
        """Execute the partition fix operation."""
        if resume:
            self.stdout.write(
                self.style.WARNING(
                    f"RESUME MODE: Resuming partition fix for {year:04d}-{month:02d} "
                    f"(data range: {start_date} to {end_date})"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Fixing partition for {year:04d}-{month:02d} (data range: {start_date} to {end_date})"
                )
            )

        logger.info(f"Target date range: {start_date} to {end_date}")
        logger.info(f"Partition table: {partition_table}")
        logger.info(f"Resume mode: {resume}")

        # Prepare SQL references
        partition_table_ref = safe_table_reference(schema, partition_name)
        parent_table_ref = safe_table_reference(schema, table_name)
        default_table_ref = safe_table_reference(schema, f"{table_name}_default")
        check_constraint_name = f"{partition_name}_partition_check"

        try:
            # Check partition state
            partition_state = self._get_partition_state(logger, schema, partition_name)

            if partition_state == "attached":
                self.stdout.write(
                    self.style.WARNING(f"Partition {partition_table} is already attached to parent table.")
                )
                # Just move any remaining data from default
                total_moved = self._move_remaining_data_to_attached_partition(
                    logger=logger,
                    default_table_ref=default_table_ref,
                    partition_table_ref=partition_table_ref,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif partition_state == "exists_unattached":
                if not resume:
                    raise CommandError(
                        f"Partition {partition_table} exists but is not attached. Use --resume to continue."
                    )
                self.stdout.write(self.style.SUCCESS(f"Found unattached partition: {partition_table}"))

                # Count existing rows
                count_sql = psycopg2_sql.SQL("SELECT COUNT(*) FROM {table};").format(table=partition_table_ref)
                result = execute_sql_query(query=count_sql, logger=logger, fetch_type=FetchType.ONE)
                existing_rows = result[0] if result else 0
                self.stdout.write(self.style.SUCCESS(f"Partition already contains {existing_rows:,} rows"))

                # Continue with moving data and attaching
                total_moved = self._complete_partition_setup(
                    logger=logger,
                    schema=schema,
                    partition_name=partition_name,
                    partition_table=partition_table,
                    partition_table_ref=partition_table_ref,
                    parent_table_ref=parent_table_ref,
                    default_table_ref=default_table_ref,
                    start_date=start_date,
                    end_date=end_date,
                    check_constraint_name=check_constraint_name,
                    existing_rows=existing_rows,
                )
            else:
                # Partition doesn't exist - create from scratch
                if resume:
                    raise CommandError(
                        f"Resume mode requires partition {partition_table} to exist, but it was not found. "
                        f"Run without --resume to start fresh."
                    )

                total_moved = self._create_partition_from_scratch(
                    logger=logger,
                    schema=schema,
                    partition_name=partition_name,
                    partition_table=partition_table,
                    partition_table_ref=partition_table_ref,
                    parent_table_ref=parent_table_ref,
                    default_table_ref=default_table_ref,
                    start_date=start_date,
                    end_date=end_date,
                    check_constraint_name=check_constraint_name,
                )

            # Vacuum analyze if enabled
            if analyze and total_moved > 0:
                self.stdout.write(self.style.SUCCESS("Running VACUUM ANALYZE..."))
                vacuum_sql = vacuum_analyze_query(schema=schema, table_name=table_name)
                execute_sql_query(query=vacuum_sql, logger=logger, fetch_type=FetchType.NONE)
                logger.info("VACUUM ANALYZE completed")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully fixed partition for {year:04d}-{month:02d}. Total rows in partition: {total_moved:,}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fixing partition: {e}"))
            logger.exception("Failed to fix partition")
            try:
                rollback(logger=logger)
                self.stdout.write(self.style.WARNING("Rolled back transaction"))
            except Exception:
                pass
            raise

    def _get_partition_state(self, logger, schema: str, partition_name: str) -> str:
        """Check if partition exists and whether it's attached."""
        # Check if table exists
        check_exists_sql = """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s;
        """
        exists_result = execute_sql_query(
            query=check_exists_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, partition_name)
        )

        if not exists_result or exists_result[0] == 0:
            return "not_exists"

        # Check if attached
        check_attached_sql = """
            SELECT COUNT(*)
            FROM pg_inherits i
            JOIN pg_class c ON i.inhrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s AND c.relname = %s;
        """
        attached_result = execute_sql_query(
            query=check_attached_sql, logger=logger, fetch_type=FetchType.ONE, params=(schema, partition_name)
        )

        if attached_result and attached_result[0] > 0:
            return "attached"
        return "exists_unattached"

    def _create_partition_from_scratch(
        self,
        logger,
        schema: str,
        partition_name: str,
        partition_table: str,
        partition_table_ref,
        parent_table_ref,
        default_table_ref,
        start_date: str,
        end_date: str,
        check_constraint_name: str,
    ) -> int:
        """Create partition from scratch and move data."""
        # Step 1: Create unattached partition table
        self.stdout.write(self.style.SUCCESS(f"Step 1/4: Creating unattached partition: {partition_table}"))
        create_sql = psycopg2_sql.SQL("CREATE TABLE {partition} (LIKE {parent} INCLUDING ALL);").format(
            partition=partition_table_ref, parent=parent_table_ref
        )
        execute_sql_query(query=create_sql, logger=logger, fetch_type=FetchType.NONE)
        logger.info(f"Created unattached partition: {partition_table}")

        return self._complete_partition_setup(
            logger=logger,
            schema=schema,
            partition_name=partition_name,
            partition_table=partition_table,
            partition_table_ref=partition_table_ref,
            parent_table_ref=parent_table_ref,
            default_table_ref=default_table_ref,
            start_date=start_date,
            end_date=end_date,
            check_constraint_name=check_constraint_name,
            existing_rows=0,
        )

    def _complete_partition_setup(
        self,
        logger,
        schema: str,
        partition_name: str,
        partition_table: str,
        partition_table_ref,
        parent_table_ref,
        default_table_ref,
        start_date: str,
        end_date: str,
        check_constraint_name: str,
        existing_rows: int,
    ) -> int:
        """Complete partition setup: move data, add constraint, attach."""
        # Step 2: Move data from default to partition (loop for concurrent inserts)
        self.stdout.write(self.style.SUCCESS("Step 2/4: Moving data from default to partition..."))

        total_rows_moved = 0
        move_iteration = 0
        max_iterations = 100

        count_default_sql = psycopg2_sql.SQL(
            """
            SELECT COUNT(*)
            FROM ONLY {table}
            WHERE recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz;
        """
        ).format(table=default_table_ref)

        move_sql = psycopg2_sql.SQL(
            """
            WITH moved AS (
                DELETE FROM ONLY {default_table}
                WHERE recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz
                RETURNING *
            )
            INSERT INTO {partition_table}
            SELECT * FROM moved
            ON CONFLICT DO NOTHING;
        """
        ).format(default_table=default_table_ref, partition_table=partition_table_ref)

        while move_iteration < max_iterations:
            move_iteration += 1

            # Count rows to move
            count_result = execute_sql_query(
                query=count_default_sql, logger=logger, fetch_type=FetchType.ONE, params=(start_date, end_date)
            )
            rows_to_move = count_result[0] if count_result else 0

            if rows_to_move == 0:
                if move_iteration == 1:
                    self.stdout.write(self.style.SUCCESS("  No data in default partition to move"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"  No more rows after {move_iteration - 1} iteration(s)"))
                break

            self.stdout.write(f"  Iteration {move_iteration}: Moving {rows_to_move:,} rows...")
            logger.info(f"Move iteration {move_iteration}: {rows_to_move} rows")

            begin(logger=logger)
            execute_sql_query(query=move_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date))
            commit(logger=logger)

            total_rows_moved += rows_to_move

        if move_iteration >= max_iterations:
            raise Exception(f"Exceeded {max_iterations} iterations. Run during lower traffic period.")

        # Get total rows in partition
        count_partition_sql = psycopg2_sql.SQL("SELECT COUNT(*) FROM {table};").format(table=partition_table_ref)
        result = execute_sql_query(query=count_partition_sql, logger=logger, fetch_type=FetchType.ONE)
        total_in_partition = result[0] if result else 0

        self.stdout.write(
            self.style.SUCCESS(f"  Moved {total_rows_moved:,} rows. Partition total: {total_in_partition:,}")
        )

        # Step 3: Add CHECK constraint to new partition (validates data matches bounds)
        self.stdout.write(self.style.SUCCESS("Step 3/4: Adding CHECK constraint to new partition..."))

        # Constraint names
        default_exclude_constraint = f"{partition_name}_default_exclude"

        # Drop partition constraint if exists (for resume scenarios)
        drop_partition_check_sql = psycopg2_sql.SQL(
            "ALTER TABLE {partition} DROP CONSTRAINT IF EXISTS {constraint};"
        ).format(partition=partition_table_ref, constraint=psycopg2_sql.Identifier(check_constraint_name))
        execute_sql_query(query=drop_partition_check_sql, logger=logger, fetch_type=FetchType.NONE)

        # Add CHECK to new partition (data must be within bounds)
        add_partition_check_sql = psycopg2_sql.SQL(
            """
            ALTER TABLE {partition}
            ADD CONSTRAINT {constraint}
            CHECK (recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz);
        """
        ).format(partition=partition_table_ref, constraint=psycopg2_sql.Identifier(check_constraint_name))
        execute_sql_query(
            query=add_partition_check_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date)
        )
        logger.info(f"Added CHECK constraint to partition: {check_constraint_name}")

        # Step 4: Lock table, move final rows, add exclusion CHECK, attach partition
        # The exclusion CHECK on default must be added INSIDE the lock to prevent race condition
        self.stdout.write(self.style.SUCCESS("Step 4/4: Locking table, finalizing, and attaching..."))

        lock_sql = psycopg2_sql.SQL("LOCK TABLE {parent} IN ACCESS EXCLUSIVE MODE;").format(parent=parent_table_ref)

        final_move_sql = psycopg2_sql.SQL(
            """
            WITH moved AS (
                DELETE FROM ONLY {default_table}
                WHERE recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz
                RETURNING *
            )
            INSERT INTO {partition_table}
            SELECT * FROM moved
            ON CONFLICT DO NOTHING;
        """
        ).format(default_table=default_table_ref, partition_table=partition_table_ref)

        # Drop default exclusion constraint if exists (for resume scenarios)
        drop_default_check_sql = psycopg2_sql.SQL(
            "ALTER TABLE {default_table} DROP CONSTRAINT IF EXISTS {constraint};"
        ).format(default_table=default_table_ref, constraint=psycopg2_sql.Identifier(default_exclude_constraint))

        # Add CHECK to default partition (data must NOT be within bounds)
        # This tells PostgreSQL "no conflicting rows exist" so ATTACH skips validation scan
        add_default_check_sql = psycopg2_sql.SQL(
            """
            ALTER TABLE {default_table}
            ADD CONSTRAINT {constraint}
            CHECK (NOT (recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz));
        """
        ).format(default_table=default_table_ref, constraint=psycopg2_sql.Identifier(default_exclude_constraint))

        attach_sql = psycopg2_sql.SQL(
            "ALTER TABLE {parent} ATTACH PARTITION {partition} FOR VALUES FROM (%s) TO (%s);"
        ).format(parent=parent_table_ref, partition=partition_table_ref)

        # All in one transaction: lock -> final move -> add exclusion CHECK -> attach -> drop CHECK
        begin(logger=logger)

        self.stdout.write("  Acquiring lock on parent table...")
        execute_sql_query(query=lock_sql, logger=logger, fetch_type=FetchType.NONE)
        logger.info("Acquired ACCESS EXCLUSIVE lock on parent table")

        # Move any rows that arrived while we were waiting for the lock
        self.stdout.write("  Moving any final rows...")
        execute_sql_query(query=final_move_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date))

        # Now add the exclusion CHECK - safe because table is locked, no new rows can arrive
        self.stdout.write("  Adding exclusion CHECK to default (enables instant attach)...")
        execute_sql_query(query=drop_default_check_sql, logger=logger, fetch_type=FetchType.NONE)
        execute_sql_query(
            query=add_default_check_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date)
        )
        logger.info(f"Added exclusion CHECK constraint to default: {default_exclude_constraint}")

        self.stdout.write("  Attaching partition (should be instant)...")
        execute_sql_query(query=attach_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date))

        # Drop the temporary exclusion constraint - no longer needed after attach
        self.stdout.write("  Cleaning up temporary constraint...")
        execute_sql_query(query=drop_default_check_sql, logger=logger, fetch_type=FetchType.NONE)
        logger.info(f"Dropped temporary constraint: {default_exclude_constraint}")

        commit(logger=logger)
        logger.info(f"Attached partition: {partition_table}")

        self.stdout.write(self.style.SUCCESS(f"Partition {partition_table} attached successfully!"))

        # Get final count
        count_partition_sql = psycopg2_sql.SQL("SELECT COUNT(*) FROM {table};").format(table=partition_table_ref)
        result = execute_sql_query(query=count_partition_sql, logger=logger, fetch_type=FetchType.ONE)
        total_in_partition = result[0] if result else 0

        return total_in_partition

    def _move_remaining_data_to_attached_partition(
        self,
        logger,
        default_table_ref,
        partition_table_ref,
        start_date: str,
        end_date: str,
    ) -> int:
        """Move any remaining data from default to an already-attached partition."""
        self.stdout.write(self.style.SUCCESS("Moving any remaining data from default partition..."))

        count_sql = psycopg2_sql.SQL(
            """
            SELECT COUNT(*)
            FROM ONLY {table}
            WHERE recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz;
        """
        ).format(table=default_table_ref)

        count_result = execute_sql_query(
            query=count_sql, logger=logger, fetch_type=FetchType.ONE, params=(start_date, end_date)
        )
        rows_to_move = count_result[0] if count_result else 0

        if rows_to_move == 0:
            self.stdout.write(self.style.SUCCESS("No remaining data in default partition"))
            # Return count from partition
            partition_count = execute_sql_query(
                query=psycopg2_sql.SQL("SELECT COUNT(*) FROM {table};").format(table=partition_table_ref),
                logger=logger,
                fetch_type=FetchType.ONE,
            )
            return partition_count[0] if partition_count else 0

        self.stdout.write(f"Moving {rows_to_move:,} rows...")

        # For attached partition, we need to delete from default and insert to partition
        # Since partition is attached, inserts to parent with correct recorded_at will route there
        move_sql = psycopg2_sql.SQL(
            """
            WITH moved AS (
                DELETE FROM ONLY {default_table}
                WHERE recorded_at >= %s::timestamptz AND recorded_at < %s::timestamptz
                RETURNING *
            )
            INSERT INTO {partition_table}
            SELECT * FROM moved
            ON CONFLICT DO NOTHING;
        """
        ).format(default_table=default_table_ref, partition_table=partition_table_ref)

        begin(logger=logger)
        execute_sql_query(query=move_sql, logger=logger, fetch_type=FetchType.NONE, params=(start_date, end_date))
        commit(logger=logger)

        # Get total in partition
        partition_count = execute_sql_query(
            query=psycopg2_sql.SQL("SELECT COUNT(*) FROM {table};").format(table=partition_table_ref),
            logger=logger,
            fetch_type=FetchType.ONE,
        )
        total = partition_count[0] if partition_count else 0

        self.stdout.write(self.style.SUCCESS(f"Moved {rows_to_move:,} rows. Partition total: {total:,}"))
        return total
