"""
PosgreSQL util functions.
"""

from enum import Enum
from logging import Logger
from typing import Any, Dict, List

from django.db import ProgrammingError, connection


class PartmanEditableConfigKey(Enum):
    """
    Supported Partman config keys to update.
    """

    INFINITE_TIME_PARTITIONS = "infinite_time_partitions"
    PREMAKE = "premake"

    def __str__(self):
        return self.value


class FetchType(Enum):
    """
    How should we fetch the results when executing the SQL query?

    Values:
        NONE: fetch nothing
        ONE: fetch one row as tuple
        ALL: fetch all as tuples
        ONE_DICT: fetch one row as a dict
        ALL_DICT: fetch all as a list of dicts
    """

    NONE = "none"
    ONE = "one"
    ALL = "all"
    ONE_DICT = "one_dict"
    ALL_DICT = "all_dict"

    def __str__(self):
        return self.value


class PSQLExtension(Enum):
    """
    PSQL extensions that can be used in our PosgreSQL instances.

    Values:
        PG_PARTMAN: pg_partman (partition management)
    """

    # Partition Management
    PG_PARTMAN = "pg_partman"


def dictfetchall(cursor) -> List[Dict[str, Any]]:
    """
    Return all rows from a db cursor as a list of dicts.
    """
    desc = cursor.description
    return [dict(zip([col[0] for col in desc], row)) for row in cursor.fetchall()]


def dictfetchone(cursor) -> Dict[str, Any]:
    """
    Return one row from a cursor as a dict.
    """
    desc = cursor.description
    return dict(zip([col[0] for col in desc], cursor.fetchone()))


def execute_sql_query(query: str, logger: Logger, fetch_type: FetchType = FetchType.NONE) -> Any:
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
        result (Any):  returns the sql result as a string or dict or None.

    Raises:
        ProgrammingError: when the SQL query cannot be executed.
    """
    with connection.cursor() as cursor:
        try:
            cursor.execute(query)
        except ProgrammingError as e:
            logger.exception(f"programming error")
            raise e
        if fetch_type is FetchType.ONE:
            return cursor.fetchone()
        elif fetch_type is FetchType.ALL:
            return cursor.fetchall()
        elif fetch_type is FetchType.ALL_DICT:
            return dictfetchall(cursor)
        elif fetch_type is FetchType.ONE_DICT:
            return dictfetchone(cursor)
        elif fetch_type is FetchType.NONE:
            return None


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


def partman_get_config_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query string to get the current config for partman.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    parent_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"SELECT * FROM partman.part_config WHERE parent_table = '{parent_table}';"


def partman_update_config_premake_query(schema: str, table_name: str, premake: int) -> str:
    """
    Create the SQL query string for updating a pg_partman config on the
    partition table represented by `schema` and `table_name`. Setting the premake entry to a new value.

    Args:
        schema (str): psql schema where the partitioned table is stored.
        `public` is the default one in psql.
        table_name (str): name of the partitioned parent table.
        premake (int): new value of premake to set. Should be > 0.

    Raises:
        AssertionError: when premake <= 0

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    assert premake > 0, "premake should be greater than 0"
    parent_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"UPDATE partman.part_config SET premake = {premake} WHERE parent_table = '{parent_table}';"


def partman_update_config_infinite_time_partitions_query(
    schema: str,
    table_name: str,
    infinite_time_partitions: bool,
) -> str:
    """
    Create the SQL query string for updating a pg_partman config on the
    partition table represented by `schema` and `table_name`. Setting the infinite_time_partitions entry to a new value.

    Args:
        schema (str): psql schema where the partitioned table is stored.
        `public` is the default one in psql.
        table_name (str): name of the partitioned parent table.
        infinite_time_partitions (bool): new value of infinite_time_partitions to set.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    parent_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"UPDATE partman.part_config SET infinite_time_partitions = {infinite_time_partitions} WHERE parent_table = '{parent_table}';"


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
