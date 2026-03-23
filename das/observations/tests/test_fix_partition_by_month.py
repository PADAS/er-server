"""Tests for fix_partition_by_month management command (partition column option)."""

import pytest

from django.core.management import CommandError, call_command


def test_fix_partition_by_month_rejects_invalid_partition_column():
    """Invalid --partition-column must raise CommandError (only recorded_at and start_recorded_at allowed)."""
    with pytest.raises(CommandError) as exc_info:
        call_command(
            "fix_partition_by_month",
            table="observations_observation",
            partition_column="invalid_column",
            year=2024,
            month=1,
        )
    assert "Partition column must be one of" in str(exc_info.value)
    assert "invalid_column" in str(exc_info.value)


def test_fix_partition_by_month_accepts_start_recorded_at():
    """--partition-column start_recorded_at is accepted (ObservationSegment use case)."""
    # Dry-run against non-existent table may fail later; we only check the option is accepted
    from observations.management.commands.fix_partition_by_month import (
        PARTITION_COLUMN_WHITELIST,
    )

    assert "start_recorded_at" in PARTITION_COLUMN_WHITELIST
    assert "recorded_at" in PARTITION_COLUMN_WHITELIST
