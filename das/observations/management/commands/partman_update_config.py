"""
Management command to update partman configuration.

Only a subset of configuration entries are currently supported via this
command: `premake` and `infinite_time_partitions`.
"""

import logging
from logging import Logger
from typing import Any

from django.core.management import BaseCommand

from utils.db.postgresql import (
    FetchType,
    PartmanEditableConfigKey,
    PSQLExtension,
    begin,
    commit,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_get_config_query,
    partman_update_config_infinite_partition_times_query,
    partman_update_config_premake_query,
    rollback,
)


class Command(BaseCommand):
    help = """Using pg_partman to create partitions ahead of time manually. It
    is useful when the `partman.run_maintenance_proc` procedure did not run
    successfully"""

    def partman_cast_str_value(
        self,
        partman_editable_config_key: PartmanEditableConfigKey,
        str_value: str,
        logger: Logger,
    ) -> Any:
        """
        Cast the partman config value to the appropriate type matching
        the `partman.part_config` psql table.

        Args:
            partman_editable_config_key (PartmanEditableConfigKey):
            associated key
            str_value (str): value as a string. Usually hydrated from
            the CLI parser.

        Output:
            value: typed value - str_value is casted to the appropriate
            type based on the provided key

        Raises:
            Exception: when it is not possible to cast or the casting is
            not yet implemented.
        """
        exception = Exception(f"Not possible to cast: {partman_editable_config_key} with value {str_value}.")
        if partman_editable_config_key == PartmanEditableConfigKey.INFINITE_TIME_PARTITIONS:
            if str_value == "true":
                return True
            elif str_value == "false":
                return False
            else:
                raise exception
        elif partman_editable_config_key == PartmanEditableConfigKey.PREMAKE:
            try:
                return int(str_value)
            except:
                raise exception
        else:
            logger.warning(f"Not yet implemented for key: {partman_editable_config_key}")
            raise exception

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
            "--key",
            type=PartmanEditableConfigKey,
            choices=list(PartmanEditableConfigKey),
            help="table column to update",
            required=True,
        )
        parser.add_argument(
            "--value",
            help="table column value to update",
            required=True,
        )

    def handle(self, *args, **options):

        logger = logging.getLogger(__name__)

        logger.info(f"options: {options} - args: {args}")

        schema = options["schema"]
        table_name = options["table"]
        key = options["key"]
        str_value = options["value"]
        value = self.partman_cast_str_value(
            partman_editable_config_key=key,
            str_value=str_value,
            logger=logger,
        )
        logger.info(f"Updating key {key} with value {value}")

        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            self.stdout.write(self.style.WARNING(f"pg_partman is not installed, skipping..."))
        else:
            try:
                begin(logger=logger)
                sql_query_show_config = partman_get_config_query(schema=schema, table_name=table_name)
                initial_configset_results = execute_sql_query(
                    query=sql_query_show_config,
                    logger=logger,
                    fetch_type=FetchType.ONE_DICT,
                )
                logger.info(f"initial config set: {initial_configset_results}")

                if key == PartmanEditableConfigKey.PREMAKE:
                    sql_query = partman_update_config_premake_query(
                        schema=schema,
                        table_name=table_name,
                        premake=value,
                    )
                    logger.info(f"executing the following SQL query: {sql_query}")
                    execute_sql_query(query=sql_query, logger=logger, fetch_type=FetchType.NONE)

                elif key == PartmanEditableConfigKey.INFINITE_TIME_PARTITIONS:
                    sql_query = partman_update_config_infinite_partition_times_query(
                        schema=schema,
                        table_name=table_name,
                        infinite_time_partitions=value,
                    )
                    logger.info(f"executing the following SQL query: {sql_query}")
                    execute_sql_query(query=sql_query, logger=logger, fetch_type=FetchType.NONE)
                else:
                    logger.warning(f"not yet implemented for key: {key}")

                final_configset_results = execute_sql_query(
                    query=sql_query_show_config,
                    logger=logger,
                    fetch_type=FetchType.ONE_DICT,
                )
                logger.info(f"final config set: {final_configset_results}")
                commit(logger=logger)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Could not update partman config - {e}"))
                rollback(logger=logger)
