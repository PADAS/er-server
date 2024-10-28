"""
Helper to create Celery tasks for the DB in general, not related to a
particular Model.
"""

from logging import Logger

from .postgresql import (
    FetchType,
    PSQLExtension,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_partition_maintenance_proc_query,
    partman_partition_maintenance_query,
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
            logger.exception(f"cannot run partition maintenance on table {table_name}")


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
            execute_sql_query(maintenance_query, logger=logger, fetch=False)
            logger.info(f"partman partition maintenance procedure done")
        except:
            logger.exception(f"cannot run the partition maintenance procedure.")
