"""
Helper to create Celery tasks for the DB in general, not related to a
particular Model.
"""

from datetime import datetime
from logging import Logger

from dateutil import relativedelta

from .postgresql import (
    FetchType,
    PSQLExtension,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_fully_qualified_default_table,
    partman_get_config_query,
    partman_list_partitions_query,
    partman_partition_maintenance_proc_query,
    partman_partition_maintenance_query,
    to_fully_qualified_table_name,
)


def run_partition_maintenance(schema: str, table_name: str, logger: Logger) -> None:
    """
    Run the partition maintenance on the provided `schema` and `table_name`.
    It uses pg_partman behind the scene so make sure to make this postgresql
    extension available before running it. It logs a warning if the extension
    is not available.

    Args:
        table_name (str): postgresql table name to run the maintenance on.
        logger (logging.Logger): logger to write to.
    """
    logger.info(f"Running partition maintenance for '{schema}.{table_name}'")
    is_pg_partman_extension_available = is_postgresql_extension_installed(
        psql_extension=PSQLExtension.PG_PARTMAN,
        logger=logger,
    )
    if not is_pg_partman_extension_available:
        logger.warning("pg_partman is not installed, cannot run the maintenance")
    else:
        try:
            maintenance_query = partman_partition_maintenance_query(schema=schema, table_name=table_name)
            logger.info(f"maintenance_query to run: {maintenance_query}")
            execute_sql_query(maintenance_query, logger=logger, fetch_type=FetchType.NONE)
            logger.info(f"partman partition maintenance done on table '{schema}.{table_name}'")
        except:
            logger.exception(f"cannot run partition maintenance on table '{schema}.{table_name}'")


def run_partition_maintenance_proc(logger: Logger) -> None:
    """
    Run the pg_partman partition maintenance procedure.
    More context here: https://github.com/pgpartman/pg_partman/blob/4.7.1/doc/pg_partman.md#maintenance-functions
    It is the preferred method for PG11+ to run partition maintenance vs
    directly calling the `run_maintenance` function.

    It uses pg_partman behind the scene so make sure to make this postgresql
    extension available before running it. It logs a warning if the extension
    is not available.

    Args:
        logger (logging.Logger): logger to write to.
    """
    logger.info(f"Running the partition maintenance procedure")
    is_pg_partman_extension_available = is_postgresql_extension_installed(
        psql_extension=PSQLExtension.PG_PARTMAN,
        logger=logger,
    )
    if not is_pg_partman_extension_available:
        logger.warning("pg_partman is not installed, cannot run the maintenance procedure")
    else:
        try:
            maintenance_query = partman_partition_maintenance_proc_query()
            logger.info(f"maintenance_query to run: {maintenance_query}")
            execute_sql_query(maintenance_query, logger=logger, fetch_type=FetchType.NONE)
            logger.info(f"partman partition maintenance procedure done")
        except:
            logger.exception(f"cannot run the partition maintenance procedure.")


def run_partition_table_check(schema: str, table_name: str, logger: Logger) -> None:
    """
    Run some checks on the partition table. If it does not comply with these
    sanity checks, it logs an error message.

    - Check that the default partition is empty, if not, it means that the
      partitions are not being created properly.
    - Check that the `infinite_time_partitions` partman config is set to True.
    - Check that the `premake` partman config is >= 3.
    - Check that the number of desired future partitions matches the
      `partman.part_config` table.

    It logs failed checks as errors which can be picked up by our monitoring
    system and dispatch alerts.

    Args:
        schema (str): psql schema where the partitioned table is stored.
        `public` is the default one in psql.
        table_name (str): name of the partitioned parent table.
        logger (Logger): logger to write to.
    """
    if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
        logger.info(f"`pg_partman` is not installed... skipping!")
    else:
        result_partitions = execute_sql_query(
            query=partman_list_partitions_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ALL_DICT,
        )
        result_partman_config = execute_sql_query(
            query=partman_get_config_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ONE_DICT,
        )
        fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
        fully_qualified_default_partition = partman_fully_qualified_default_table(
            schema=schema,
            table_name=table_name,
        )
        default_table_count_query = f"SELECT COUNT(*) FROM {fully_qualified_default_partition};"
        result_default_table_count = execute_sql_query(
            query=default_table_count_query,
            logger=logger,
            fetch_type=FetchType.ONE_DICT,
        )

        # Computing the future partitions that should be have been created
        future_partition_table_names = set()
        already_created_partition_table_names = {
            f"{e['partition_schemaname']}.{e['partition_tablename']}" for e in result_partitions
        }

        now = datetime.now()

        for i in range(result_partman_config["premake"] - 1):
            partition_start_date = now + relativedelta.relativedelta(months=i)
            fully_qualified_time_partition = (
                f"{fully_qualified_table_name}_p{partition_start_date.year:04d}_{partition_start_date.month:02d}"
            )
            future_partition_table_names.add(fully_qualified_time_partition)

        missing_partition_table_names = future_partition_table_names.difference(already_created_partition_table_names)

        # Error Messages
        errors = []

        # Prefix used to create a monitor and alert in our infrastructure
        prefix_message = "ER Partman:"
        error_default_table_count = {
            "message": f"{prefix_message} The default table {fully_qualified_default_partition} contains {result_default_table_count['count']} rows. It should be empty. Make sure that the partitions are being created ahead of time."
        }
        error_partman_config_infinite_time_partitions = {
            "message": f"{prefix_message} The partman config `infinite_time_partitions` is set to False. It must be set to True to make partitions ahead of time with the maintenance procedure."
        }
        error_partman_config_premake_small = {
            "message": f"{prefix_message} The partman config `premake` is too small. It must be >=3 and is currently set to {result_partman_config['premake']}."
        }
        error_missing_partitions = {
            "message": f"{prefix_message} Missing {len(missing_partition_table_names)} partitions given the `premake` attribute set to {result_partman_config['premake']}, namely: {missing_partition_table_names}"
        }

        # Sanity checks
        if result_default_table_count["count"] > 0:
            errors.append(error_default_table_count)

        if not result_partman_config["infinite_time_partitions"]:
            errors.append(error_partman_config_infinite_time_partitions)

        if result_partman_config["premake"] < 3:
            errors.append(error_partman_config_premake_small)

        if len(missing_partition_table_names) > 0:
            errors.append(error_missing_partitions)

        if len(errors) == 0:
            logger.info(f"{schema}.{table_name} partition table: ✅")
        else:
            for error in errors:
                logger.error(error["message"])
