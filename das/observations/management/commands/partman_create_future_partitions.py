"""
Management command to manually create partitions for the
observations_observation table.

By default, it creates the partitions for the next 3 months (not including the
current one). It is possible to call the script with some parameters to change
the offset and the number of partitions to create manually. See --help.
"""

import logging
from datetime import datetime
from logging import Logger
from typing import Any, Dict, List, Set, Tuple

import pytz
from dateutil.relativedelta import relativedelta

from django.core.management import BaseCommand

from utils.db.postgresql import (
    FetchType,
    PSQLExtension,
    begin,
    commit,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_create_monthly_partition_time_query,
    partman_list_partitions_query,
    rollback,
    to_fully_qualified_table_name,
)


class Command(BaseCommand):
    help = """Using pg_partman to create partitions ahead of time manually. It
    is useful when the `partman.run_maintenance_proc` procedure did not run
    successfully"""

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            type=str,
            help="psql schema to target",
            default="public",
        )
        parser.add_argument(
            "-t",
            "--table",
            type=str,
            help="psql table to target",
            default="observations_observation",
        )
        parser.add_argument(
            "-n",
            "--number",
            type=int,
            help="Number of partitions to create",
            default=3,
        )
        parser.add_argument(
            "--offset",
            type=int,
            help="month offset to start creating partitions (current_month + offset)",
            default=0,
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Run in dry-run mode (no changes made)",
        )

    def run_sanity_checks(
        self,
        expected_new_count: int,
        initial_metadata: Dict[str, Any],
        final_metadata: Dict[str, Any],
        logger: Logger,
    ) -> None:
        """
        Run some sanity checks and returns whether we can commit the transaction.

        Args:
            expected_new_count: The number of partitions we expected to create (excluding already existing ones).
            initial_metadata: Metadata collected before partition creation.
            final_metadata: Metadata collected after partition creation.
            logger: Logger instance.

        Raises:
            AssertionError: when one sanity check does not pass.
        """
        logger.info(f"checking initial_metadata {initial_metadata} against final_metadata {final_metadata}")

        required_keys = ["partitions", "counts"]

        assert all(key in initial_metadata for key in required_keys), "Missing keys in initial_metadata"
        assert all(key in final_metadata for key in required_keys), "Missing keys in final_metadata"

        # Checking that the number of new partitions match what we expected to create
        set_created_partitions = final_metadata["partitions"] - initial_metadata["partitions"]

        assert expected_new_count == len(
            set_created_partitions
        ), f"expected to create {expected_new_count} partitions but created {len(set_created_partitions)}"

        # Data integrity checks
        assert initial_metadata["counts"] <= final_metadata["counts"], "some rows were dropped"

    def collect_metadata_for_sanity_check(
        self,
        schema: str,
        table_name: str,
        logger: Logger,
    ) -> Dict[str, Any]:
        """
        Probe the state of the DB to collect metadata. That is used by the
        sanity check function to check data integrity.

        Args:
            schema (str): psql schema where the table is stored. `public` is
            the default one in psql.
            table_name (str): name of the psql table.
            logger (logging.Logger): The logger to use to write potential
            errors.

        Outputs:
            partitions (set[str]): set of all the partitions on the
            `schema.table_name`.
            counts (int): count of the number of entries in
            `schema.table_name`.
        """
        result = {}
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)

        counts_result = execute_sql_query(
            query=f"SELECT COUNT(*) FROM {fully_qualified_table};",
            logger=logger,
            fetch_type=FetchType.ONE,
        )

        partitions_result = execute_sql_query(
            query=partman_list_partitions_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ALL_DICT,
        )

        if partitions_result:
            result["partitions"] = {p["partition_tablename"] for p in partitions_result}

        if counts_result:
            result["counts"] = counts_result[0]

        return result

    def calculate_partitions_to_create(
        self,
        table_name: str,
        number_partitions: int,
        offset: int,
        existing_partitions: Set[str],
        now: datetime,
        logger: Logger,
    ) -> Tuple[List[Tuple[int, int]], List[str]]:
        """
        Calculate which partitions need to be created, skipping ones that already exist.

        Args:
            table_name: Name of the table (without schema).
            number_partitions: Total number of partitions requested.
            offset: Month offset from current month.
            existing_partitions: Set of existing partition table names.
            now: Current datetime.
            logger: Logger instance.

        Returns:
            Tuple of (list of (year, month) tuples to create, list of skipped partition names)
        """
        partitions_to_create = []
        skipped_partitions = []

        for i in range(number_partitions):
            partition_start_date = (now + relativedelta(months=1 + (i + offset))).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            year = partition_start_date.year
            month = partition_start_date.month

            # pg_partman naming convention: {table_name}_p{year}_{month:02d}
            partition_name = f"{table_name}_p{year:04d}_{month:02d}"

            if partition_name in existing_partitions:
                logger.info(f"Partition {partition_name} already exists, skipping")
                skipped_partitions.append(partition_name)
            else:
                partitions_to_create.append((year, month))

        return partitions_to_create, skipped_partitions

    def handle(self, *args, **options):

        logger = logging.getLogger(__name__)

        logger.info(f"options: {options} - args: {args}")

        schema = options["schema"]
        table_name = options["table"]
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
        number_partitions = options["number"]
        offset = options["offset"]
        is_dry_run = options["dry_run"]
        now = datetime.now(tz=pytz.utc)

        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            self.stdout.write(self.style.WARNING("pg_partman is not installed, skipping..."))
        else:
            try:
                logger.info(
                    f"Attempt to create {number_partitions} new partitions on {fully_qualified_table} with an offset of {offset} month(s) from now."
                )
                begin(logger=logger)
                initial_metadata = self.collect_metadata_for_sanity_check(
                    schema=schema,
                    table_name=table_name,
                    logger=logger,
                )
                logger.info(f"Initial metadata: {initial_metadata}")

                # Calculate which partitions need to be created (skip existing ones)
                partitions_to_create, skipped_partitions = self.calculate_partitions_to_create(
                    table_name=table_name,
                    number_partitions=number_partitions,
                    offset=offset,
                    existing_partitions=initial_metadata.get("partitions", set()),
                    now=now,
                    logger=logger,
                )

                if skipped_partitions:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping {len(skipped_partitions)} partitions that already exist: {skipped_partitions}"
                        )
                    )

                if not partitions_to_create:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"All {number_partitions} requested partitions already exist. Nothing to create."
                        )
                    )
                    rollback(logger=logger)
                    return

                # Create only the partitions that don't exist
                for year, month in partitions_to_create:
                    sql_query = partman_create_monthly_partition_time_query(
                        schema=schema,
                        table_name=table_name,
                        year=year,
                        month=month,
                    )

                    logger.info(f"SQL query to create the partition: {sql_query}")
                    execute_sql_query(
                        query=sql_query,
                        logger=logger,
                        fetch_type=FetchType.NONE,
                    )

                final_metadata = self.collect_metadata_for_sanity_check(
                    schema=schema,
                    table_name=table_name,
                    logger=logger,
                )

                self.run_sanity_checks(
                    expected_new_count=len(partitions_to_create),
                    initial_metadata=initial_metadata,
                    final_metadata=final_metadata,
                    logger=logger,
                )

                created_partitions = final_metadata["partitions"] - initial_metadata["partitions"]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created {len(created_partitions)} new partitions in {fully_qualified_table}: {created_partitions}"
                    )
                )

                if is_dry_run:
                    logger.info(
                        f"Dry Run Mode: Rolling back the transaction. Undoing the {len(partitions_to_create)} new partitions on the table {schema}.{table_name}"
                    )
                    rollback(logger=logger)
                else:
                    commit(logger=logger)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Could not create the requested partitions: {e}"))
                rollback(logger=logger)
