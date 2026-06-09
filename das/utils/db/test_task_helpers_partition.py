"""Tests for run_partition_table_check future-partition detection.

These tests verify the boundary-count rewrite: the check compares expected
month-starts against the partition start times reported by pg_partman, so it is
immune to pg_partman naming/version differences (4.x `_pYYYY_MM` vs 5.x
`_pYYYYMMDD`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from dateutil import relativedelta

from utils.db import task_helpers


def _boundary_rows(start: datetime, count: int) -> list[dict[str, datetime]]:
    """Build ALL_DICT-shaped boundary rows starting at `start` for `count` months.

    Mirrors pg_partman 5.x behaviour: `child_start_time` is a timezone-aware
    month-start timestamptz.
    """
    return [
        {"child_start_time": (start + relativedelta.relativedelta(months=i)).replace(tzinfo=timezone.utc)}
        for i in range(count)
    ]


class TestRunPartitionTableCheck:
    def test_does_not_log_missing_when_all_future_partitions_present(self) -> None:
        """Regression: with pg_partman 5.x `YYYYMMDD`-style boundaries present for the
        current and upcoming months, no "Missing ... partitions" error is logged."""
        logger = MagicMock(spec=logging.Logger)
        fixed_now = datetime(2026, 6, 6, 12, 0, 0)
        config = {"premake": 5, "infinite_time_partitions": False, "retention": None}
        # premake=5 -> expects current month + next 3 (range(premake - 1) == 4 months).
        boundaries = _boundary_rows(start=datetime(2026, 6, 1), count=6)

        with patch("utils.db.task_helpers.is_postgresql_extension_installed", return_value=True):
            with patch("utils.db.task_helpers.execute_sql_query") as mock_execute:
                with patch("utils.db.task_helpers.datetime") as mock_datetime:
                    mock_datetime.now.return_value = fixed_now
                    mock_execute.side_effect = [boundaries, config]
                    task_helpers.run_partition_table_check(
                        schema="public",
                        table_name="observations_observationsegment",
                        logger=logger,
                    )

        error_messages = [call[0][0] for call in logger.error.call_args_list]
        assert not any(
            "Missing" in str(m) for m in error_messages
        ), f"Expected no missing-partition error, got: {error_messages}"

    def test_logs_missing_when_a_future_month_boundary_is_absent(self) -> None:
        """When a required future month's boundary is missing, the error is logged and
        names the correct `YYYY-MM`."""
        logger = MagicMock(spec=logging.Logger)
        fixed_now = datetime(2026, 6, 6, 12, 0, 0)
        config = {"premake": 5, "infinite_time_partitions": False, "retention": None}
        # Present: 2026-06, 2026-07, 2026-09. Missing the required 2026-08.
        boundaries = [
            {"child_start_time": datetime(2026, 6, 1, tzinfo=timezone.utc)},
            {"child_start_time": datetime(2026, 7, 1, tzinfo=timezone.utc)},
            {"child_start_time": datetime(2026, 9, 1, tzinfo=timezone.utc)},
        ]

        with patch("utils.db.task_helpers.is_postgresql_extension_installed", return_value=True):
            with patch("utils.db.task_helpers.execute_sql_query") as mock_execute:
                with patch("utils.db.task_helpers.datetime") as mock_datetime:
                    mock_datetime.now.return_value = fixed_now
                    mock_execute.side_effect = [boundaries, config]
                    task_helpers.run_partition_table_check(
                        schema="public",
                        table_name="observations_observationsegment",
                        logger=logger,
                    )

        error_messages = [str(call[0][0]) for call in logger.error.call_args_list]
        missing_errors = [m for m in error_messages if "Missing" in m]
        assert len(missing_errors) == 1, f"Expected one missing-partition error, got: {error_messages}"
        assert "ER Partman:" in missing_errors[0]
        assert "public.observations_observationsegment" in missing_errors[0]
        assert "2026-08" in missing_errors[0]
        assert "2026-06" not in missing_errors[0]
        assert "2026-07" not in missing_errors[0]

    def test_logs_premake_too_small_error(self) -> None:
        """premake < 3 is reported regardless of partition boundaries."""
        logger = MagicMock(spec=logging.Logger)
        fixed_now = datetime(2026, 6, 6, 12, 0, 0)
        config = {"premake": 2, "infinite_time_partitions": False, "retention": None}
        boundaries = _boundary_rows(start=datetime(2026, 6, 1), count=4)

        with patch("utils.db.task_helpers.is_postgresql_extension_installed", return_value=True):
            with patch("utils.db.task_helpers.execute_sql_query") as mock_execute:
                with patch("utils.db.task_helpers.datetime") as mock_datetime:
                    mock_datetime.now.return_value = fixed_now
                    mock_execute.side_effect = [boundaries, config]
                    task_helpers.run_partition_table_check(
                        schema="public",
                        table_name="observations_observationsegment",
                        logger=logger,
                    )

        error_messages = [str(call[0][0]) for call in logger.error.call_args_list]
        assert any("`premake` is too small" in m for m in error_messages), error_messages
        assert any("public.observations_observationsegment" in m for m in error_messages), error_messages

    def test_skips_when_pg_partman_not_installed(self) -> None:
        """When pg_partman is not installed the check logs nothing as an error."""
        logger = MagicMock(spec=logging.Logger)
        with patch("utils.db.task_helpers.is_postgresql_extension_installed", return_value=False):
            with patch("utils.db.task_helpers.execute_sql_query") as mock_execute:
                task_helpers.run_partition_table_check(
                    schema="public",
                    table_name="observations_observationsegment",
                    logger=logger,
                )
        mock_execute.assert_not_called()
        logger.error.assert_not_called()
