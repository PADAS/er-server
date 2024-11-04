"""
PosgreSQL util functions.
"""

import math
import re
from enum import Enum
from logging import Logger
from typing import Any, Dict, List, Tuple

import scipy.stats as stats
from psycopg2 import sql as psycopg2_sql

import scipy.stats as stats

from django.db import ProgrammingError, connection

# Pattern to validate SQL identifiers (schema names, table names, column names)
# Allows alphanumeric characters and underscores, must start with letter or underscore
SQL_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PartmanEditableConfigKey(Enum):
    """
    Supported Partman config keys to update.
    """

    INFINITE_TIME_PARTITIONS = "infinite_time_partitions"
    PREMAKE = "premake"

    def __str__(self):
        return self.value


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


def validate_sql_identifier(identifier: str, identifier_type: str = "identifier") -> None:
    """
    Validate that a string is a safe SQL identifier.

    Args:
        identifier: The identifier to validate
        identifier_type: Type of identifier for error messages (e.g., "table name", "schema")

    Raises:
        ValueError: If the identifier contains unsafe characters
    """
    if not SQL_IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(
            f"Invalid SQL {identifier_type}: '{identifier}'. "
            f"Must contain only alphanumeric characters and underscores, "
            f"and must start with a letter or underscore."
        )


def safe_sql_identifier(identifier: str) -> psycopg2_sql.Identifier:
    """
    Create a safely quoted SQL identifier using psycopg2.

    Args:
        identifier: The identifier (table name, schema, column name) to quote

    Returns:
        A psycopg2.sql.Identifier that will be properly quoted when composed
    """
    validate_sql_identifier(identifier, "identifier")
    return psycopg2_sql.Identifier(identifier)


def safe_table_reference(schema: str, table_name: str) -> psycopg2_sql.Composed:
    """
    Create a safely quoted fully-qualified table reference.

    Args:
        schema: The schema name
        table_name: The table name

    Returns:
        A psycopg2.sql.Composed object representing schema.table_name
    """
    validate_sql_identifier(schema, "schema")
    validate_sql_identifier(table_name, "table name")
    return psycopg2_sql.SQL("{}.{}").format(
        psycopg2_sql.Identifier(schema),
        psycopg2_sql.Identifier(table_name),
    )


def execute_sql_query(
    query: str | psycopg2_sql.Composed,
    logger: Logger,
    fetch_type: FetchType = FetchType.NONE,
    params: Tuple | None = None,
) -> Any:
    """
    Execute the SQL `query`. Return one row if `fetch` is set to True.
    The process/thread is exited on execution error and an exception is written
    with the `logger`.

    Args:
        query: SQL query string or psycopg2.sql.Composed object to be executed.
        logger (logging.Logger): The logger to use to write potential errors.
        fetch_type (FetchType): Should we return one row, all or nothing of the
            results? Defaults to returning Nothing.
        params: Optional tuple of parameters to safely substitute into the query.
            Use %s placeholders in the query for each parameter.

    Output:
        result (Any):  returns the sql result as a string or dict or None.

    Raises:
        ProgrammingError: when the SQL query cannot be executed.
    """
    with connection.cursor() as cursor:
        try:
            cursor.execute(query, params)
        except ProgrammingError as e:
            logger.exception("programming error")
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
    sql_query = "SELECT COUNT(*) FROM pg_extension WHERE extname = %s;"
    try:
        sql_result = execute_sql_query(
            query=sql_query,
            logger=logger,
            fetch_type=FetchType.ONE,
            params=(psql_extension.value,),
        )
        return bool(sql_result and sql_result[0] == 1)
    except Exception:
        logger.exception(f"cannot execute sql query with extension: {psql_extension.value}")
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
    sql_query = "SELECT extversion FROM pg_extension WHERE extname = %s;"
    try:
        sql_result = execute_sql_query(
            query=sql_query,
            logger=logger,
            fetch_type=FetchType.ONE,
            params=(psql_extension.value,),
        )
        return sql_result[0] if sql_result else None
    except Exception:
        logger.exception(f"cannot execute sql query with extension: {psql_extension.value}")
        return None


def to_fully_qualified_table_name(schema: str, table_name: str) -> str:
    """
    Given the psql `schema` and a `table_name`, it returns a fully qualified
    table_name.

    Validates both schema and table_name to prevent SQL injection.

    >>> public.observations_observation

    Raises:
        ValueError: If schema or table_name contain invalid characters.
    """
    validate_sql_identifier(schema, "schema")
    validate_sql_identifier(table_name, "table name")
    return f"{schema}.{table_name}"


def partman_partition_maintenance_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query string for running the partman partition maintenance.

    Args:
        schema (str): Name of the psql schema.
        table_name (str): Name of the postgresql table to run partman
        maintenance on.

    Raises:
        ValueError: If schema or table_name contain invalid characters.
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

    Raises:
        ValueError: If schema or table_name contain invalid characters.
        AssertionError: If year or month are out of valid range.
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
    Create the SQL query string for running the partman show_partitions function.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#show_partitions

    Args:
        schema (str): Name of the psql schema. eg. public.
        table_name (str): Name of the psql table to target.

    Raises:
        ValueError: If schema or table_name contain invalid characters.
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

    Raises:
        ValueError: If schema, table_name, column_name, or order_by contain invalid characters.
        AssertionError: If limit exceeds 1,000,000.
    """
    assert limit <= 1_000_000, "the limit parameter should be lower than 1M."

    # Validate all identifiers
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    validate_sql_identifier(column_name, "column name")
    validate_sql_identifier(order_by, "order_by column")

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
    jobmon: bool = None,
    debug: bool = None,
) -> str:
    """
    Create the SQL query for running the partman partition maintenance procedure.

    Only parameters that differ from pg_partman defaults are included in the query
    for maximum compatibility across pg_partman versions.

    Args:
        wait (int): Time in seconds to wait between partition set maintenance runs. Default 0.
        analyze (bool): Whether to run ANALYZE after creating child tables. If None, uses
            pg_partman default behavior. Default None.
        jobmon (bool): Whether to use pg_jobmon for logging. If None, uses pg_partman default (true).
        debug (bool): Whether to enable debug notices. If None, uses pg_partman default (false).

    More information: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#run_maintenance_proc
    """
    # Build parameter list dynamically - only include non-default parameters for version compatibility
    params = []

    # p_wait: only include if non-zero
    if wait != 0:
        params.append(f"p_wait := {wait}")

    # p_analyze: include if explicitly set (NULL is the pg_partman default)
    if analyze is not None:
        params.append(f"p_analyze := {str(analyze).upper()}")

    # p_jobmon: only include if explicitly set to False (True is the pg_partman default)
    if jobmon is not None and jobmon is False:
        params.append(f"p_jobmon := FALSE")

    # p_debug: only include if explicitly set to True (False is the pg_partman default)
    if debug is not None and debug is True:
        params.append(f"p_debug := TRUE")

    params_str = ", ".join(params)
    return f"CALL partman.run_maintenance_proc({params_str});"


def _validate_interval(interval: str) -> None:
    """
    Validate that an interval string is safe for use in SQL.

    Args:
        interval: PostgreSQL interval string (e.g., '1 week', '1 month')

    Raises:
        ValueError: If the interval contains potentially dangerous characters.
    """
    # Allow only alphanumeric, spaces, and common interval characters
    if not re.match(r"^[a-zA-Z0-9\s]+$", interval):
        raise ValueError(f"Invalid interval format: '{interval}'")


def _validate_order(order: str) -> None:
    """
    Validate that an order string is ASC or DESC.

    Args:
        order: Sort order string

    Raises:
        ValueError: If the order is not ASC or DESC.
    """
    if order.upper() not in ("ASC", "DESC"):
        raise ValueError(f"Invalid order: '{order}'. Must be 'ASC' or 'DESC'.")


def partman_partition_data_proc_query(
    schema: str,
    table_name: str,
    p_loop_count: int = None,
    p_interval: str = None,
    p_lock_wait: int = 0,
    p_wait: int = 1,
    p_order: str = "ASC",
    p_quiet: bool = False,
) -> str:
    """
    Create the SQL query string for running the partman partition data procedure.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_proc

    Args:
        schema (str): psql schema where the table is stored. `public` is the
            default one in psql.
        table_name (str): name of the psql table.
        p_loop_count (int): Number of times to loop through moving data. Default None (run until complete).
        p_interval (str): Interval to use for batching data moves. Default None (uses partition interval).
        p_lock_wait (int): Time in seconds to wait for locks. Default 0.
        p_wait (int): Time in seconds to wait between partition set data moves. Default 1.
        p_order (str): Order to process data. 'ASC' or 'DESC'. Default 'ASC'.
        p_quiet (bool): Suppress notice messages. Default False.

    Raises:
        ValueError: If schema, table_name, p_interval, or p_order contain invalid characters.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    _validate_order(p_order)

    # Build the parameter list
    params = [f"'{fully_qualified_table_name}'"]

    if p_loop_count is not None:
        params.append(f"p_loop_count := {int(p_loop_count)}")

    if p_interval is not None:
        _validate_interval(p_interval)
        params.append(f"p_interval := '{p_interval}'")

    params.append(f"p_lock_wait := {int(p_lock_wait)}")
    params.append(f"p_wait := {int(p_wait)}")
    params.append(f"p_order := '{p_order.upper()}'")
    params.append(f"p_quiet := {str(p_quiet).upper()}")

    params_str = ", ".join(params)
    return f"CALL partman.partition_data_proc({params_str});"


def partman_partition_data_time_query(
    schema: str,
    table_name: str,
    p_batch_count: int = None,
    p_batch_interval: str = None,
    p_lock_wait: float = None,
    p_order: str = None,
    p_analyze: bool = None,
    p_source_table: str = None,
) -> str:
    """
    Create the SQL query string for running partman partition_data_time.
    More information here: https://github.com/pgpartman/pg_partman/blob/master/doc/pg_partman.md#partition_data_time

    Only parameters that differ from pg_partman defaults are included in the query
    for maximum compatibility across pg_partman versions.

    Args:
        schema (str): psql schema where the table is stored. `public` is the
            default one in psql.
        table_name (str): name of the psql table.
        p_batch_count (int): Number of times to run the batch in a single call.
            Default is 1 in pg_partman.
        p_batch_interval (str): Interval of time to process per batch (e.g., '1 week').
            If None, uses control column's partition interval.
        p_lock_wait (float): Amount of time in seconds to wait for locks.
            Default is 0 in pg_partman.
        p_order (str): Order to process data. 'ASC' or 'DESC'. Default 'ASC' in pg_partman.
        p_analyze (bool): Run ANALYZE after moving data. Default True in pg_partman.
        p_source_table (str): Fully qualified source table name to migrate from.
            If None, migrates all data from parent default partition.

    Raises:
        ValueError: If any identifiers or interval contain invalid characters.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)

    # Build the parameter list - first param is required, cast to text for type safety
    params = [f"'{fully_qualified_table_name}'::text"]

    # Only include optional parameters that differ from pg_partman defaults
    if p_batch_count is not None:
        params.append(f"p_batch_count := {int(p_batch_count)}")

    if p_batch_interval is not None:
        _validate_interval(p_batch_interval)
        params.append(f"p_batch_interval := '{p_batch_interval}'::interval")

    if p_lock_wait is not None:
        params.append(f"p_lock_wait := {float(p_lock_wait)}")

    # p_order: only include if not 'ASC' (the default)
    if p_order is not None and p_order.upper() != "ASC":
        _validate_order(p_order)
        params.append(f"p_order := '{p_order.upper()}'::text")

    # p_analyze: only include if explicitly False (True is the default)
    if p_analyze is not None and p_analyze is False:
        params.append("p_analyze := FALSE")

    if p_source_table:
        # p_source_table is a fully qualified table name (schema.table)
        # Validate it by splitting and validating each part
        if "." in p_source_table:
            source_parts = p_source_table.split(".", 1)
            validate_sql_identifier(source_parts[0], "source schema")
            validate_sql_identifier(source_parts[1], "source table name")
        else:
            validate_sql_identifier(p_source_table, "source table name")
        params.append(f"p_source_table := '{p_source_table}'::text")

    params_str = ", ".join(params)
    return f"SELECT partman.partition_data_time({params_str});"


def partman_get_config_query(schema: str, table_name: str) -> str:
    """
    Create the SQL query string to get the current config for partman.

    Args:
        schema (str): Name of the psql schema.
        table_name (str): Name of the psql table.

    Raises:
        ValueError: If schema or table_name contain invalid characters.
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
        ValueError: If schema or table_name contain invalid characters.
    """
    assert premake > 0, "premake should be greater than 0"
    parent_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"UPDATE partman.part_config SET premake = {int(premake)} WHERE parent_table = '{parent_table}';"


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

    Raises:
        ValueError: If schema or table_name contain invalid characters.
    """
    parent_table = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    bool_value = "TRUE" if infinite_time_partitions else "FALSE"
    return (
        f"UPDATE partman.part_config SET infinite_time_partitions = {bool_value} WHERE parent_table = '{parent_table}';"
    )


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


def partman_update_config_infinite_partition_times_query(
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

    Raises:
        ValueError: If schema or table_name contain invalid characters.
    """
    fully_qualified_table_name = to_fully_qualified_table_name(schema=schema, table_name=table_name)
    return f"VACUUM ANALYZE {fully_qualified_table_name};"


def partman_fully_qualified_default_table(schema: str, table_name: str) -> str:
    """
    Return the fully qualified default table name for the provided schema and
    table_name.

    Args:
        schema (str): psql schema where the table is stored.
        table_name (str): name of the psql table.

    Raises:
        ValueError: If schema or table_name contain invalid characters.
    """
    # Validate and construct the default table name
    validate_sql_identifier(schema, "schema")
    validate_sql_identifier(table_name, "table name")
    return f"{schema}.{table_name}_default"


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
