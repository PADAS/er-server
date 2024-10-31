"""
Django management command to run `partman.partition_data_time()` on the
observations_observation table.

More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_time

Some sanity checks are run before and after running the partman function to
ensure data integrity.
"""

import logging
from logging import Logger
from typing import Any, Dict

from django.core.management import BaseCommand

from utils.db.postgresql import (
    FetchType,
    PSQLExtension,
    begin,
    commit,
    execute_sql_query,
    is_postgresql_extension_installed,
    md5_over_column_query,
    partman_list_partitions_query,
    partman_partition_data_time_query,
    rollback,
    to_fully_qualified_table_name,
    vacuum_analyze_query,
)


class Command(BaseCommand):
    help = """Using pg_partman to run the `partman.partition_data_time()`. It is
    useful for backfilling missing partitions.

    More information available here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_time"""

    def run_sanity_checks(
        self,
        initial_metadata: Dict[str, Any],
        final_metadata: Dict[str, Any],
        logger: Logger,
    ) -> None:
        """
        Run some sanity checks and returns whether we can commit the transaction.

        The following checks are run:

        1. The number of elements in the default partition table is 0.
        2. The number of elements before moving the data to new partition
        tables and after match.
        3. Every partition that was not created should contain the same number
        of elements before and after.
        4. Every partition that was not created should have the same md3 before
        and after.

        Raises:
            AssertionError: when one sanity check does not pass.
        """
        logger.info(f"checking initial_metadata {initial_metadata} against final_metadata {final_metadata}")

        required_keys = ["partition_table_names", "partition", "counts", "counts_default_partition"]
        assert all(key in initial_metadata for key in required_keys), "Missing keys in initial_metadata"
        assert all(key in final_metadata for key in required_keys), "Missing keys in final_metadata"

        set_created_partitions = set(final_metadata["partition_table_names"]) - set(
            initial_metadata["partition_table_names"]
        )

        logger.info(f"created partitions {set_created_partitions}")

        # Data integrity checks
        assert final_metadata["counts_default_partition"] == 0, "The number of rows in the default partition is not 0!"
        assert initial_metadata["counts"] == final_metadata["counts"], "The number of observation rows has changed!"

        # Checking that no data is altered in partitions that were not touched
        for partition_table_name in initial_metadata["partition_table_names"]:
            assert (
                partition_table_name in initial_metadata["partition"]
            ), f"Missing key `partition.{partition_table_name}`."
            assert (
                initial_metadata["partition"][partition_table_name]["counts"]
                == final_metadata["partition"][partition_table_name]["counts"]
            ), f"The table {partition_table_name} contains more rows than expected."
            assert (
                initial_metadata["partition"][partition_table_name]["md5"]
                == final_metadata["partition"][partition_table_name]["md5"]
            ), f"The table {partition_table_name} contains altered data."

    def collect_metadata_for_sanity_check(self, schema: str, table_name: str, logger: Logger) -> Dict[str, Any]:
        """
        Probe the state of the DB to collect metadata. That is used by the
        sanity check function to check data integrity.

        Outputs:
            md5 (str): md5 hash of all the id column values in the `schema.table_name`.
            partitions (set[str]): set of all the partitions on the `schema.table_name`.
            counts (int): count of the number of entries in `schema.table_name`.
        """
        result = {"partition": {}, "partition_table_names": []}
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)

        counts_result = execute_sql_query(
            query=f"SELECT COUNT(*) FROM {fully_qualified_table};",
            logger=logger,
            fetch_type=FetchType.ONE,
        )

        counts_default_result = execute_sql_query(
            query=f"SELECT COUNT(*) FROM {fully_qualified_table}_default;",
            logger=logger,
            fetch_type=FetchType.ONE,
        )

        partitions_result = execute_sql_query(
            query=partman_list_partitions_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ALL_DICT,
        )

        partition_tablenames = [p["partition_tablename"] for p in partitions_result]

        for partition_tablename in partition_tablenames:
            result["partition"][partition_tablename] = {"counts": None, "md5": None}

            counts_partition_result = execute_sql_query(
                query=f"SELECT COUNT(*) FROM {to_fully_qualified_table_name(schema=schema, table_name=partition_tablename)};",
                logger=logger,
                fetch_type=FetchType.ONE,
            )
            md5_partition_result = execute_sql_query(
                query=md5_over_column_query(
                    schema=schema,
                    table_name=partition_tablename,
                    column_name="id",
                ),
                logger=logger,
                fetch_type=FetchType.ONE,
            )

            if counts_partition_result:
                result["partition"][partition_tablename]["counts"] = counts_partition_result[0]
                result["partition"][partition_tablename]["md5"] = md5_partition_result[0]

        if partitions_result:
            result["partition_table_names"] = partition_tablenames

        if counts_result:
            result["counts"] = counts_result[0]

        if counts_default_result:
            result["counts_default_partition"] = counts_default_result[0]

        return result

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            type=str,
            help="psql schema to select",
            default="public",
        )
        parser.add_argument(
            "-t",
            "--table",
            type=str,
            help="psql table",
            default="observations_observation",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Run in dry-run mode (no changes made)",
        )

    def handle(self, *args, **options):

        logger = logging.getLogger(__name__)

        logger.info(f"options: {options}")
        logger.info(f"args: {args}")
        schema = options["schema"]
        table_name = options["table"]
        is_dry_run = options["dry_run"]
        fully_qualified_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)

        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            self.stdout.write(self.style.WARNING(f"pg_partman is not installed, skipping..."))
        else:
            logger.info(f"pg_partman is properly installed.")
            sql_query = partman_partition_data_time_query(schema=schema, table_name=table_name)

            try:
                begin(logger=logger)
                initial_metadata = self.collect_metadata_for_sanity_check(
                    schema=schema,
                    table_name=table_name,
                    logger=logger,
                )

                # Data partition
                logger.info(f'running the partition_data_time() function with: "{sql_query}" - It can be slow...')
                execute_sql_query(query=sql_query, logger=logger, fetch_type=FetchType.NONE)

                final_metadata = self.collect_metadata_for_sanity_check(
                    schema=schema,
                    table_name=table_name,
                    logger=logger,
                )

                self.run_sanity_checks(
                    initial_metadata=initial_metadata,
                    final_metadata=final_metadata,
                    logger=logger,
                )

                set_created_partitions = set(final_metadata["partition_table_names"]) - set(
                    initial_metadata["partition_table_names"]
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully ran the data partition procedure, created {len(set_created_partitions)} new partitions on table {fully_qualified_table}: {set_created_partitions}"
                    )
                )

                if is_dry_run:
                    number_partitions = len(set_created_partitions)
                    logger.info(
                        f"Dry Run Mode: Rolling back the transaction. Undoing the {number_partitions} new partition(s) on the table '{fully_qualified_table}': {set_created_partitions}"
                    )
                    rollback(logger=logger)
                else:

                    commit(logger=logger)

                    # Vacuuming
                    vacuum_analyze_sql_query = vacuum_analyze_query(schema=schema, table_name=table_name)
                    logger.info(f'running the vacuuming with: "{vacuum_analyze_sql_query}"')
                    execute_sql_query(query=vacuum_analyze_sql_query, logger=logger, fetch_type=FetchType.NONE)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Could not execute the following query: "{sql_query}". Error: {e}'))
                rollback(logger=logger)
