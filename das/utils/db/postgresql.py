"""
PosgreSQL util functions.
"""

from enum import Enum
from logging import Logger
from typing import Optional

from django.db import ProgrammingError, connection


class PSQLExtension(Enum):
    """
    PSQL extensions that can be used in our PosgreSQL instances.
    """

    # Partition Management
    PG_PARTMAN = "pg_partman"


def execute_sql_query(query: str, logger: Logger, fetch: bool = True) -> Optional[str]:
    """
    Execute the SQL `query`. Return one row if `fetch` is set to True.
    The process/thread is exited on execution error and an exception is written
    with the `logger`. It can raise a ProgrammingError exception.

    Args:
        query (str): SQL query string to be executed. Should contain a `;` at the end.
        logger (logging.Logger): The logger to use to write potential errors.
        fetch (bool): Should we return one row of the results? Defaults to
        `True`.

    Output:
        result (Optional[str]) | ProgrammingError:  returns the sql result as a
        string or raise an exception.
    """
    result = None
    with connection.cursor() as cursor:
        try:
            cursor.execute(query)
        except ProgrammingError as e:
            logger.exception(f"programming error")
            raise e
        if fetch:
            result = cursor.fetchone()
        return result


def is_postgresql_extension_installed(psql_extension: PSQLExtension, logger: Logger) -> bool:
    """
    Check whether the postgresql extension `extension_name` is installed.

    Args:
        psql_extension (PSQLExtension): Name of the PSQLExtension.
        logger (logging.Logger): logger to use to write potential execution
        errors.

    Output:
        bool: Is the extension `extension_name` installed?
    """
    sql_query = f"SELECT COUNT(*) FROM pg_extension WHERE extname = '{psql_extension.value}';"
    try:
        sql_result = execute_sql_query(
            query=sql_query,
            logger=logger,
            fetch=True,
        )
        return bool(sql_result and sql_result[0] == 1)
    except:
        logger.exception(f"cannot execute sql query: {sql_query}")
        return False


def partman_partition_maintenance_query(table_name: str) -> str:
    """
    Create the SQL query string for running the partman partition maintenance.

    Args:
        table_name (str): Name of the postgresql table to run partman
        maintenance on.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `table_name`.
    """
    return f"SELECT partman.run_maintenance('{table_name}');"


def partman_partition_maintenance_proc_query() -> str:
    """
    Create the SQL query for running the partman partition maintenance
    procedure.
    """
    return f"CALL partman.run_maintenance_proc();"


def partman_data_partition_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query string for running the partman partition data procedure.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_proc

    Args:
        schema (str): psql schema where the table is stored. `public` is the
        default one in psql.
        table_name (str): name of the psql table.
    """
    return f"CALL partman.partition_data_proc('{schema}.{table_name}');"


def vacuum_analyze_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query to vacuum analyze a table.

    Args:
        schema (str): psql schema where the table is stored. `public` is the
        default one in psql.
        table_name (str): name of the psql table.
    """
    return f"VACUUM ANALYZE {schema}.{table_name};"
