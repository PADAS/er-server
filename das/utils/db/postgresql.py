"""
PosgreSQL util functions.
"""

from logging import Logger
from typing import Optional

from django.db import ProgrammingError, connection


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
            logger.exception(f"programming error: {e}")
            raise e
        if fetch:
            result = cursor.fetchone()
        return result


def is_postgresql_extension_installed(extension_name: str, logger: Logger) -> bool:
    """
    Check whether the postgresql extension `extension_name` is installed.

    Args:
        extension_name (str): Name of the postgresql extension.
        logger (logging.Logger): logger to use to write potential execution
        errors.

    Output:
        bool: Is the extension `extension_name` installed?
    """
    try:
        sql_result = execute_sql_query(
            query=f"SELECT COUNT(*) FROM pg_extension WHERE extname = '{extension_name}';",
            logger=logger,
            fetch=True,
        )
        return bool(sql_result and sql_result[0] == 1)
    except Exception as e:
        logger.exception(f"cannot execute sql query: {e}")
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
