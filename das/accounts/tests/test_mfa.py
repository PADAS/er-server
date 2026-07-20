"""Tests for the shared MFA claim helpers in accounts.mfa."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from accounts.mfa import MFA_CLOCK_SKEW_SECONDS, mfa_time_is_fresh

_NOW_EPOCH = 1_800_000_000  # fixed reference instant (epoch seconds)


@pytest.fixture
def frozen_now():
    """Freeze accounts.mfa's clock so freshness arithmetic is deterministic."""
    fixed = datetime.fromtimestamp(_NOW_EPOCH, tz=timezone.utc)
    with patch("accounts.mfa.timezone.now", return_value=fixed):
        yield _NOW_EPOCH


class TestMfaTimeIsFresh:
    def test_returns_true_when_mfa_time_is_recent(self, frozen_now):
        assert mfa_time_is_fresh(frozen_now - 10, max_age_seconds=3600) is True

    def test_returns_false_when_mfa_time_is_older_than_max_age(self, frozen_now):
        assert mfa_time_is_fresh(frozen_now - 7200, max_age_seconds=3600) is False

    def test_returns_true_at_the_max_age_plus_skew_boundary(self, frozen_now):
        boundary = frozen_now - (3600 + MFA_CLOCK_SKEW_SECONDS)
        assert mfa_time_is_fresh(boundary, max_age_seconds=3600) is True

    def test_returns_false_just_past_the_skew_boundary(self, frozen_now):
        just_past = frozen_now - (3600 + MFA_CLOCK_SKEW_SECONDS + 1)
        assert mfa_time_is_fresh(just_past, max_age_seconds=3600) is False

    def test_returns_false_when_mfa_time_is_missing(self, frozen_now):
        assert mfa_time_is_fresh(None, max_age_seconds=3600) is False

    def test_returns_false_when_mfa_time_is_not_numeric(self, frozen_now):
        assert mfa_time_is_fresh("not-a-timestamp", max_age_seconds=3600) is False

    def test_accepts_numeric_string_epoch_seconds(self, frozen_now):
        # Claims can arrive as strings; a numeric string must be honored.
        assert mfa_time_is_fresh(str(frozen_now - 10), max_age_seconds=3600) is True

    def test_none_max_age_falls_back_to_the_default_window(self, frozen_now):
        # ~1.16 days old: fresh under the 365-day default that None resolves to.
        assert mfa_time_is_fresh(frozen_now - 100_000, max_age_seconds=None) is True

    def test_none_max_age_still_expires_past_the_default_window(self, frozen_now):
        # ~400 days old: stale even under the 365-day default (confirms the fallback isn't unbounded).
        assert mfa_time_is_fresh(frozen_now - 400 * 86_400, max_age_seconds=None) is False

    def test_returns_false_when_mfa_time_is_bool(self, frozen_now):
        # bool is an int subclass; a JSON `true` in the claim must not read as a fresh timestamp.
        assert mfa_time_is_fresh(True, max_age_seconds=3600) is False

    def test_returns_false_when_mfa_time_is_far_in_the_future(self, frozen_now):
        # A timestamp well into the future is nonsensical; fail closed rather than "fresh forever".
        assert mfa_time_is_fresh(frozen_now + 3600, max_age_seconds=3600) is False

    def test_allows_small_future_clock_skew(self, frozen_now):
        # Minor clock drift into the future (within the skew tolerance) is still fresh.
        assert mfa_time_is_fresh(frozen_now + MFA_CLOCK_SKEW_SECONDS, max_age_seconds=3600) is True

    def test_returns_false_just_past_the_future_skew_boundary(self, frozen_now):
        assert mfa_time_is_fresh(frozen_now + (MFA_CLOCK_SKEW_SECONDS + 1), max_age_seconds=3600) is False
