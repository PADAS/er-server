"""
Managemant command to manually create partitions for the
observations_observation table.

By default, it creates the partitions for the next 3 months (not including the
current one). It is possible to call the script with some parameters to change
the offset and the number of partitions to create manually. See --help.
"""

import logging
from datetime import datetime, timedelta
from logging import Logger
from typing import Any, Dict

import pytz

from django.core.management import BaseCommand

from utils.db.postgresql import (
    FetchType,
    PSQLExtension,
    begin,
    commit,
    execute_sql_query,
    is_postgresql_extension_installed,
    md5_over_column_query,
    parse_partman_partition_str,
    partman_create_monthly_partition_time_query,
    partman_show_partitions_query,
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
            default=1,
        )

    def run_sanity_checks(
        self,
        options,
        initial_metadata: Dict[str, Any],
        final_metadata: Dict[str, Any],
        logger: Logger,
    ) -> None:
        """
        Run some sanity checks and returns whether we can commit the transaction.

        Raises:
            AssertionError: when one sanity check does not pass.
        """
        logger.info(f"checking initial_metadata {initial_metadata} against final_metadata {final_metadata}")

        required_keys = ["partitions", "counts", "md5"]
        assert all(key in initial_metadata for key in required_keys), "Missing keys in initial_metadata"
        assert all(key in final_metadata for key in required_keys), "Missing keys in final_metadata"

        # Checking that the number of new partitions match what the user wanted to create
        number_partitions = options["number"]
        set_created_partitions = final_metadata["partitions"] - initial_metadata["partitions"]

        assert number_partitions == len(
            set_created_partitions
        ), "the number of created partitions does not match the number of partitions the user wants to create"

        # Data integrity checks
        assert initial_metadata["counts"] == final_metadata["counts"], "The number of observation rows has changed!"
        assert initial_metadata["md5"] == final_metadata["md5"], "The content of some rows has changed!"

    def collect_metadata_for_sanity_check(self, schema: str, table_name: str, logger: Logger) -> Dict[str, Any]:
        """
        Probe the state of the DB to collect metadata. That is used by the
        sanity check function to check data integrity.

        Outputs:
            md5 (str): md5 hash of all the id column values in the `schema.table_name`.
            partitions (set[str]): set of all the partitions on the `schema.table_name`.
            counts (int): count of the number of entries in `schema.table_name`.
        """
        result = {}
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)

        md5_result = execute_sql_query(
            query=md5_over_column_query(
                schema=schema,
                table_name=table_name,
                column_name="id",
            ),
            logger=logger,
            fetch_type=FetchType.ONE,
        )
        counts_result = execute_sql_query(
            query=f"SELECT COUNT(*) FROM {fully_qualified_table};",
            logger=logger,
            fetch_type=FetchType.ONE,
        )
        partitions_result = execute_sql_query(
            query=partman_show_partitions_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ALL,
        )

        if partitions_result:
            result["partitions"] = {parse_partman_partition_str(p[0])["table"] for p in partitions_result}

        if md5_result:
            result["md5"] = md5_result[0]

        if counts_result:
            result["counts"] = counts_result[0]

        return result

    def handle(self, *args, **options):

        logger = logging.getLogger(__name__)

        logger.info(f"options: {options} - args: {args}")

        schema = options["schema"]
        table_name = options["table"]
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
        number_partitions = options["number"]
        offset = options["offset"]
        now = datetime.now(tz=pytz.utc)

        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            self.stdout.write(self.style.WARNING(f"pg_partman is not installed, skipping..."))
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

                for i in range(number_partitions):

                    # The partition start dates are based on the current time and
                    # the offset in months.
                    partition_start_date = (now + timedelta(days=31 * (i + offset))).replace(
                        day=1,  # We reset the date to the first day of the month because not all months have 31 days.
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                    logger.info(f"Partition start date: {partition_start_date}")

                    sql_query = partman_create_monthly_partition_time_query(
                        schema=schema,
                        table_name=table_name,
                        year=partition_start_date.year,
                        month=partition_start_date.month,
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
                    options=options,
                    initial_metadata=initial_metadata,
                    final_metadata=final_metadata,
                    logger=logger,
                )

                commit(logger=logger)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created {number_partitions} new partitions in {fully_qualified_table}: {final_metadata['partitions'] - initial_metadata['partitions']}"
                    )
                )

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Could not create the requested partitions: {e}"))
                rollback(logger=logger)
