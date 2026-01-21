import pytest

from utils.db.postgresql import (
    partman_partition_data_proc_query,
    partman_partition_maintenance_proc_query,
)


def test_partman_partition_maintenance_proc_query_defaults():
    assert (
        partman_partition_maintenance_proc_query()
        == "CALL partman.run_maintenance_proc(p_wait := 0, p_analyze := NULL, p_jobmon := TRUE, p_debug := FALSE);"
    )


@pytest.mark.parametrize(
    "analyze,expected",
    [
        (
            None,
            "CALL partman.run_maintenance_proc(p_wait := 0, p_analyze := NULL, p_jobmon := TRUE, p_debug := FALSE);",
        ),
        (
            True,
            "CALL partman.run_maintenance_proc(p_wait := 0, p_analyze := TRUE, p_jobmon := TRUE, p_debug := FALSE);",
        ),
        (
            False,
            "CALL partman.run_maintenance_proc(p_wait := 0, p_analyze := FALSE, p_jobmon := TRUE, p_debug := FALSE);",
        ),
    ],
)
def test_partman_partition_maintenance_proc_query_analyze(analyze, expected):
    assert partman_partition_maintenance_proc_query(analyze=analyze) == expected


def test_partman_partition_data_proc_query_default_args():
    assert (
        partman_partition_data_proc_query(schema="public", table_name="observations_observation")
        == "CALL partman.partition_data_proc('public.observations_observation', p_wait := 0);"
    )


def test_partman_partition_data_proc_query_with_batch():
    assert (
        partman_partition_data_proc_query(schema="public", table_name="observations_observation", batch=10000, wait=1)
        == "CALL partman.partition_data_proc('public.observations_observation', p_wait := 1, p_batch := 10000);"
    )
