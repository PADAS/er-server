"""
PosgreSQL util functions.
"""

from enum import Enum
from logging import Logger
from typing import Dict, Optional

from django.db import ProgrammingError, connection


class FetchType(Enum):
    """
    How should we fetch the results when executing the SQL query?

    Values:
        NONE: fetch nothing
        ONE: fetch one row
        ALL: fetch all
    """

    NONE = "none"
    ONE = "one"
    ALL = "all"


class PSQLExtension(Enum):
    """
    PSQL extensions that can be used in our PosgreSQL instances.

    Values:
        PG_PARTMAN: pg_partman (partition management)
    """

    # Partition Management
    PG_PARTMAN = "pg_partman"


def execute_sql_query(query: str, logger: Logger, fetch_type: FetchType = FetchType.NONE) -> Optional[str]:
    """
    Execute the SQL `query`. Return one row if `fetch` is set to True.
    The process/thread is exited on execution error and an exception is written
    with the `logger`.

    Args:
        query (str): SQL query string to be executed. Should contain a `;` at the end.
        logger (logging.Logger): The logger to use to write potential errors.
        fetch_type (FetchType): Should we return one row, all or nothing of the
        results? Defaults to returning Nothing.

    Output:
        result (Optional[str]):  returns the sql result as a string or raise an
        exception.

    Raises:
        ProgrammingError: when the SQL query cannot be executed.
    """
    result = None
    with connection.cursor() as cursor:
        try:
            cursor.execute(query)
        except ProgrammingError as e:
            logger.exception(f"programming error")
            raise e
        if fetch_type is FetchType.ONE:
            result = cursor.fetchone()
        elif fetch_type is FetchType.ALL:
            result = cursor.fetchall()
        return result


def begin(logger: Logger) -> None:
    """
    Execute a BEGIN sql query.
    """
    execute_sql_query(query="BEGIN;", logger=logger, fetch_type=FetchType.NONE)


def commit(logger: Logger) -> None:
    """
    Execute a COMMIT sql query.
    """
    execute_sql_query(query="COMMIT;", logger=logger, fetch_type=FetchType.NONE)


def rollback(logger: Logger) -> None:
    """
    Execute a ROLLBACK sql query.
    """
    execute_sql_query(query="ROLLBACK;", logger=logger, fetch_type=FetchType.NONE)


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
            fetch_type=FetchType.ONE,
        )
        return bool(sql_result and sql_result[0] == 1)
    except:
        logger.exception(f"cannot execute sql query: {sql_query}")
        return False


def to_fully_qualified_table_name(schema: str, table_name: str) -> str:
    """
    Given the psql `schema` and a `table_name`, it returns a fully qualified
    table_name.

    >>> public.observations_observation
    """
    return f"{schema}.{table_name}"


def partman_partition_maintenance_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query string for running the partman partition maintenance.

    Args:
        table_name (str): Name of the postgresql table to run partman
        maintenance on.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"SELECT partman.run_maintenance('{fully_qualified_table_name}');"


def to_partition_start_time_string(year: int, month: int, day: int = 1) -> str:
    """
    Make the starting time suffix used for psql partitions with partman.

    Raises:
        AssertionError if the year, month and day parameters are not valid.

    >>> to_partition_start_time_string(year=2024, month=9)
    2025-09-01

    >>> to_partition_start_time_string(year=2024, month=9, day=8)
    2025-09-08
    """
    assert 2000 <= year <= 3000, "year should be in a valid range 2000..3000"
    assert 1 <= month <= 12, "month should be in a valid range 1..12"
    assert 1 <= day <= 31, "day should be in a valid range 1..31"

    return f"{year:04d}-{month:02d}-{day:02d}"


def partman_create_monthly_partition_time_query(schema: str, table_name: str, year: int, month: int) -> str:
    """
    Create the SQL query string for running the partman partition time function.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#create_partition_time

    Args:
        schema (str): Name of the psql schema. eg. public.
        table_name (str): Name of the psql table to target.
        year (int): year to create the partition.
        month (int): month


    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    start_time_string = to_partition_start_time_string(year=year, month=month, day=1)
    return f"""SELECT
        partman.create_partition_time(
            p_parent_table => '{fully_qualified_table_name}',
            p_partition_times => ARRAY['{start_time_string}'::DATE]
        );"""


def partman_show_partitions_query(schema: str, table_name: str) -> str:
    """
    Create thre SQL query string for running the partman show_partitions function.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#show_partitions

    Args:
        schema (str): Name of the psql schema. eg. public.
        table_name (str): Name of the psql table to target.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"SELECT partman.show_partitions('{fully_qualified_table_name}');"


def parse_partman_partition_str(partition_str: str) -> Dict[str, str]:
    """
    Parse the partition string, one row of partman_show_partitions_query when
    executed.

    Outputs:
        schema (str): psql schema
        table (str): psql partition table with the _p suffix

    >>> parse_partman_partition_str('(public,observations_observation_p2015_01)')
    {'schema': public, 'table': 'observations_observation_p2015_01'}
    """
    parts = partition_str.replace("(", "").replace(")", "").split(",")
    return {"schema": parts[0], "table": parts[1]}


def md5_over_column_query(schema: str, table_name: str, column_name: str = "id") -> str:
    """
    Create the SQL query string to check the md5 value of the concatenated
    casted values of `column_name` for the provided `schema` and `table_name`.

    Args:
        schema (str): Name of the psql schema. eg. public.
        table_name (str): Name of the psql table to target.
        column_name (str): column name to run the MD5 over. It should be
        castable as TEXT.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema`, `table_name` and `column_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"SELECT MD5(STRING_AGG(CAST({column_name} AS TEXT), '')) AS md5_hash FROM {fully_qualified_table_name};"


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

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"CALL partman.partition_data_proc('{fully_qualified_table_name}');"


def vacuum_analyze_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query to vacuum analyze a table.

    Args:
        schema (str): psql schema where the table is stored. `public` is the
        default one in psql.
        table_name (str): name of the psql table.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"VACUUM ANALYZE {fully_qualified_table_name};"
