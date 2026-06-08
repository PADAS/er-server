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
    partman_get_config_query,
    partman_list_partition_boundaries_query,
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
            prefix_message = "ER Partman:"
            logger.error(f"{prefix_message} Cannot run the partition maintenance procedure.")


def run_partition_table_check(schema: str, table_name: str, logger: Logger) -> None:
    """
    Run some checks on the partition table. If it does not comply with these
    sanity checks, it logs an error message.

    - Check that the `premake` partman config is >= 3.
    - Check that all expected future monthly partitions exist. The expected
      months are compared against the actual partition start times reported by
      pg_partman (on `(year, month)` tuples), so the check does not depend on
      the partition naming scheme and is immune to pg_partman version changes.

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
        result_boundaries = execute_sql_query(
            query=partman_list_partition_boundaries_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ALL_DICT,
        )
        result_partman_config = execute_sql_query(
            query=partman_get_config_query(schema=schema, table_name=table_name),
            logger=logger,
            fetch_type=FetchType.ONE_DICT,
        )

        premake = result_partman_config["premake"]
        now = datetime.now()

        # Compare on (year, month) tuples rather than partition names so the
        # check is immune to pg_partman naming/version differences. We also
        # avoid comparing datetimes directly: `child_start_time` is timezone
        # aware while `datetime.now()` is naive.
        expected_month_starts = {
            (start_date.year, start_date.month)
            for i in range(premake - 1)
            for start_date in [now + relativedelta.relativedelta(months=i)]
        }
        actual_month_starts = {
            (row["child_start_time"].year, row["child_start_time"].month) for row in result_boundaries
        }
        missing_month_starts = expected_month_starts.difference(actual_month_starts)

        # Error Messages
        errors = []

        # Prefix used to create a monitor and alert in our infrastructure
        prefix_message = "ER Partman:"
        error_partman_config_premake_small = {
            "message": f"{prefix_message} [{schema}.{table_name}] The partman config `premake` is too small. It must be >=3 and is currently set to {premake}."
        }
        missing_months_readable = sorted(f"{year:04d}-{month:02d}" for year, month in missing_month_starts)
        error_missing_partitions = {
            "message": f"{prefix_message} [{schema}.{table_name}] Missing {len(missing_month_starts)} partitions given the `premake` attribute set to {premake}, namely: {missing_months_readable}"
        }

        # Sanity checks
        # Note: data in the default partition is allowed, so we skip that check.
        # Note: infinite_time_partitions is intentionally off to avoid creating
        # partitions far into the future due to future-dated data in the default table.

        if premake < 3:
            errors.append(error_partman_config_premake_small)

        if len(missing_month_starts) > 0:
            errors.append(error_missing_partitions)

        if len(errors) == 0:
            logger.info(f"{schema}.{table_name} partition table: ✅")
        else:
            for error in errors:
                logger.error(error["message"])
