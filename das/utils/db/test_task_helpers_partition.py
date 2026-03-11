"""Tests for run_partition_table_check with retention (infinite_time_partitions = false)."""

import logging
from unittest.mock import MagicMock, patch

from utils.db import task_helpers


def test_run_partition_table_check_does_not_error_on_infinite_time_partitions_when_retention_set():
    """When partman config has retention set, infinite_time_partitions=false should not be reported as error."""
    logger = MagicMock(spec=logging.Logger)
    config_with_retention = {
        "premake": 5,
        "infinite_time_partitions": False,
        "retention": "3 years",
    }
    with patch("utils.db.task_helpers.is_postgresql_extension_installed", return_value=True):
        with patch("utils.db.task_helpers.execute_sql_query") as mock_execute:
            mock_execute.side_effect = [
                [],  # result_partitions (list)
                config_with_retention,  # result_partman_config (ONE_DICT)
                {"count": 0},  # result_default_table_count
            ]
            task_helpers.run_partition_table_check(
                schema="public",
                table_name="observations_observationsegment",
                logger=logger,
            )
    error_messages = [call[0][0] for call in logger.error.call_args_list]
    infinite_msg = "infinite_time_partitions"
    assert not any(
        infinite_msg in str(m) for m in error_messages
    ), "Should not log infinite_time_partitions error when retention is set"


def test_run_partition_table_check_errors_on_infinite_time_partitions_when_retention_not_set():
    """When partman config has infinite_time_partitions=false and no retention, error is logged."""
    logger = MagicMock(spec=logging.Logger)
    config_no_retention = {
        "premake": 5,
        "infinite_time_partitions": False,
        "retention": None,
    }
    with patch("utils.db.task_helpers.is_postgresql_extension_installed", return_value=True):
        with patch("utils.db.task_helpers.execute_sql_query") as mock_execute:
            mock_execute.side_effect = [
                [],  # result_partitions
                config_no_retention,  # result_partman_config
                {"count": 0},  # result_default_table_count
            ]
            task_helpers.run_partition_table_check(
                schema="public",
                table_name="some_table",
                logger=logger,
            )
    error_messages = [call[0][0] for call in logger.error.call_args_list]
    assert any("infinite_time_partitions" in str(m) for m in error_messages)
