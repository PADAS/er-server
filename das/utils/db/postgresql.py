"""
PosgreSQL util functions.
"""

import math
from enum import Enum
from logging import Logger
from typing import Any, Dict, List

import scipy.stats as stats

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
        BTREE_GIST: btree_gist (GiST index support for btree-equivalent data types)
    """

    # Partition Management
    PG_PARTMAN = "pg_partman"
    # GiST index support for btree-equivalent data types (required for GIST indexes on timestamp columns)
    BTREE_GIST = "btree_gist"


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


def get_postgresql_extension_version(psql_extension: PSQLExtension, logger: Logger) -> str:
    """
    Get the version of a postgresql extension.

    Args:
        psql_extension (PSQLExtension): Name of the PSQLExtension.
        logger (logging.Logger): logger to use to write potential execution
        errors.

    Output:
        str: The version string of the extension, or None if not found.
    """
    sql_query = f"SELECT extversion FROM pg_extension WHERE extname = '{psql_extension.value}';"
    try:
        sql_result = execute_sql_query(
            query=sql_query,
            logger=logger,
            fetch_type=FetchType.ONE,
        )
        return sql_result[0] if sql_result else None
    except:
        logger.exception(f"cannot execute sql query: {sql_query}")
        return None


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


def to_monthly_partition_table_name(schema: str, table_name: str, year: int, month: int) -> str:
    """
    Construct the partition table name for a monthly partitioned table.

    For pg_partman monthly partitions, the naming convention is:
    {schema}.{table_name}_p{year}_{month:02d}

    Args:
        schema (str): psql schema where the table is stored. `public` is the
        default one in psql.
        table_name (str): name of the parent partitioned table.
        year (int): year of the partition (2000-3000)
        month (int): month of the partition (1-12)

    Returns:
        str: Fully qualified partition table name

    Raises:
        AssertionError: if the year or month parameters are not valid.

    Example:
        >>> to_monthly_partition_table_name("public", "observations_observation", 2024, 9)
        'public.observations_observation_p2024_09'
    """
    assert 2000 <= year <= 3000, "year should be in a valid range 2000..3000"
    assert 1 <= month <= 12, "month should be in a valid range 1..12"

    partition_suffix = f"_p{year:04d}_{month:02d}"
    return to_fully_qualified_table_name(schema=schema, table_name=f"{table_name}{partition_suffix}")


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


def partman_list_partitions_query(schema: str, table_name: str) -> str:
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
    return f"SELECT * FROM partman.show_partitions('{fully_qualified_table_name}');"


def md5_over_column_query(
    schema: str,
    table_name: str,
    order_by: str,
    column_name: str = "id",
    limit: int = 1000,
) -> str:
    """
    Create the SQL query string to check the md5 value of the concatenated
    casted values of `column_name` for the provided `schema` and `table_name`.

    Args:
        schema (str): Name of the psql schema. eg. public.
        table_name (str): Name of the psql table to target.
        order_by (str): Column name to order by. Usually the primary key or an
        index.
        limit (int): limit of the query, defaults to 1000.
        column_name (str): column name to run the MD5 over. It should be
        castable as TEXT.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema`, `table_name`, `column_name`, `order_by` and `limit`.
    """
    assert limit <= 1_000_000, "the limit parameter should be lower than 1M."

    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"""
    SELECT
      MD5(STRING_AGG(CAST({column_name} AS TEXT), '')) AS md5_hash
    FROM
      {fully_qualified_table_name}
    GROUP BY
      {order_by}
    ORDER BY
      {order_by}
    LIMIT
      {limit}
    ;"""


def partman_partition_maintenance_proc_query(
    wait: int = 0,
    analyze: bool = None,
    jobmon: bool = True,
    debug: bool = False,
) -> str:
    """
    Create the SQL query for running the partman partition maintenance procedure.

    Args:
        wait (int): Time in seconds to wait between partition set maintenance runs. Default 0.
        analyze (bool): Whether to run ANALYZE after creating child tables. If None, uses
            pg_partman default behavior. Default None.
        jobmon (bool): Whether to use pg_jobmon for logging. Default True.
        debug (bool): Whether to enable debug notices. Default False.

    More information: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#run_maintenance_proc
    """
    # Build parameter string - p_analyze accepts NULL for default behavior
    analyze_str = "NULL" if analyze is None else str(analyze).upper()

    return (
        f"CALL partman.run_maintenance_proc("
        f"p_wait := {wait}, "
        f"p_analyze := {analyze_str}, "
        f"p_jobmon := {str(jobmon).upper()}, "
        f"p_debug := {str(debug).upper()});"
    )


def partman_partition_data_proc_query(
    schema: str,
    table_name: str,
    p_wait: int = 0,
    p_batch: int = None,
    p_order: str = "ASC",
    p_analyze: bool = True,
    p_source_table: str = None,
) -> str:
    """
    Create the SQL query string for running the partman partition data procedure.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_proc

    Args:
        schema (str): psql schema where the table is stored. `public` is the
            default one in psql.
        table_name (str): name of the psql table.
        p_wait (int): Time in seconds to wait between commits. Default 0.
        p_batch (int): Limit the number of batches moved in a single call. Default None (no limit).
        p_order (str): Order to process data. 'ASC' or 'DESC'. Default 'ASC'.
        p_analyze (bool): Run ANALYZE after moving data. Default True.
        p_source_table (str): Specific child partition table to migrate from.
            If None, migrates all data from parent default partition.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)

    # Build the parameter list
    params = [f"'{fully_qualified_table_name}'"]
    params.append(f"p_wait := {p_wait}")

    if p_batch is not None:
        params.append(f"p_batch := {p_batch}")

    params.append(f"p_order := '{p_order}'")
    params.append(f"p_analyze := {str(p_analyze).upper()}")

    if p_source_table:
        params.append(f"p_source_table := '{p_source_table}'")

    params_str = ", ".join(params)
    return f"CALL partman.partition_data_proc({params_str});"


def partman_partition_data_time_query(
    schema: str,
    table_name: str,
    p_batch_count: int = None,
    p_batch_interval: str = None,
    p_lock_wait: float = None,
    p_order: str = "ASC",
    p_analyze: bool = True,
    p_jobmon: bool = True,
    p_source_table: str = None,
) -> str:
    """
    Create the SQL query string for running partman partition_data_time.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_time

    Args:
        schema (str): psql schema where the table is stored. `public` is the
        default one in psql.
        table_name (str): name of the psql table.
        p_batch_count (int): Number of times to run the batch in a single call.
        If None, runs until completion.
        p_batch_interval (str): Interval of time to process per batch (e.g., '1 week').
        If None, uses control column's partition interval.
        p_lock_wait (float): Amount of time in seconds to wait for locks.
        If None, waits indefinitely.
        p_order (str): Order to process data. 'ASC' or 'DESC'. Default 'ASC'.
        p_analyze (bool): Run ANALYZE after moving data. Default True.
        p_jobmon (bool): Use jobmon for logging. Default True.
        p_source_table (str): Specific child partition table to migrate from.
        If None, migrates all data from parent default partition.

    Note: This does not check for SQL injection. Make sure to know what you are
    doing with `schema` and `table_name`.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)

    # Build the parameter list
    params = [f"'{fully_qualified_table_name}'"]

    if p_batch_count is not None:
        params.append(f"p_batch_count := {p_batch_count}")

    if p_batch_interval is not None:
        params.append(f"p_batch_interval := '{p_batch_interval}'")

    if p_lock_wait is not None:
        params.append(f"p_lock_wait := {p_lock_wait}")

    params.append(f"p_order := '{p_order}'")
    params.append(f"p_analyze := {str(p_analyze).upper()}")
    params.append(f"p_jobmon := {str(p_jobmon).upper()}")

    if p_source_table:
        params.append(f"p_source_table := '{p_source_table}'")

    params_str = ", ".join(params)
    return f"SELECT partman.partition_data_time({params_str});"


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


def partman_fully_qualified_default_table(schema: str, table_name: str) -> str:
    """
    Return the fully qualified default table name for the provided schema and
    table_name.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"{fully_qualified_table_name}_default"


def get_sample_size(population_size: int, confidence_level: float, margin_of_error: float):
    """
    Calculate the sample size required to stay within a given confidence level and margin of error.

    Args:
        population_size (int): The total size of the population.
        confidence_level (float): The desired confidence level, typically 0.90, 0.95, or 0.99.
        margin_of_error (float): The desired margin of error, expressed as a decimal.

    Returns:
        int: The required sample size.
    """
    # Calculate the z-score for the given confidence level
    z_score = stats.norm.ppf(1 - (1 - confidence_level) / 2)

    # Calculate the sample size
    sample_size = (z_score**2 * population_size) / (z_score**2 + (population_size - 1) * (margin_of_error**2))

    return math.ceil(sample_size)
