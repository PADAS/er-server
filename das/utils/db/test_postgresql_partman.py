import pytest

from utils.db.postgresql import (
    partman_partition_data_proc_query,
    partman_partition_maintenance_proc_query,
)


def test_partman_partition_maintenance_proc_query_defaults():
    """With no arguments, should produce minimal call for maximum version compatibility."""
    assert partman_partition_maintenance_proc_query() == "CALL partman.run_maintenance_proc();"


@pytest.mark.parametrize(
    "analyze,expected",
    [
        (
            None,
            "CALL partman.run_maintenance_proc();",
        ),
        (
            True,
            "CALL partman.run_maintenance_proc(p_analyze := TRUE);",
        ),
        (
            False,
            "CALL partman.run_maintenance_proc(p_analyze := FALSE);",
        ),
    ],
)
def test_partman_partition_maintenance_proc_query_analyze(analyze, expected):
    assert partman_partition_maintenance_proc_query(analyze=analyze) == expected


def test_partman_partition_maintenance_proc_query_wait():
    """p_wait should only be included when non-zero."""
    assert partman_partition_maintenance_proc_query(wait=5) == "CALL partman.run_maintenance_proc(p_wait := 5);"


def test_partman_partition_maintenance_proc_query_jobmon_false():
    """p_jobmon should only be included when explicitly set to False."""
    assert (
        partman_partition_maintenance_proc_query(jobmon=False)
        == "CALL partman.run_maintenance_proc(p_jobmon := FALSE);"
    )


def test_partman_partition_maintenance_proc_query_debug_true():
    """p_debug should only be included when explicitly set to True."""
    assert partman_partition_maintenance_proc_query(debug=True) == "CALL partman.run_maintenance_proc(p_debug := TRUE);"


def test_partman_partition_maintenance_proc_query_all_params():
    """When all params are explicitly set, they should all be included."""
    assert (
        partman_partition_maintenance_proc_query(wait=10, analyze=True, jobmon=False, debug=True)
        == "CALL partman.run_maintenance_proc(p_wait := 10, p_analyze := TRUE, p_jobmon := FALSE, p_debug := TRUE);"
    )


def test_partman_partition_data_proc_query_default_args():
    assert (
        partman_partition_data_proc_query(schema="public", table_name="observations_observation")
        == "CALL partman.partition_data_proc('public.observations_observation', p_lock_wait := 0, p_wait := 1, p_order := 'ASC', p_quiet := FALSE);"
    )


def test_partman_partition_data_proc_query_with_loop_count():
    assert (
        partman_partition_data_proc_query(
            schema="public", table_name="observations_observation", p_loop_count=10000, p_wait=2
        )
        == "CALL partman.partition_data_proc('public.observations_observation', p_loop_count := 10000, p_lock_wait := 0, p_wait := 2, p_order := 'ASC', p_quiet := FALSE);"
    )
