from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from rt_api import tasks
from rt_api.pubsub_subscriptions import all_queue_names, queue_name_for


def _make_pubsub_redis_mock(list_lengths: dict[bytes, int]) -> MagicMock:
    """Return a MagicMock redis client whose list keys have the given lengths.

    ``llen()`` and a single ``scan_iter()`` (matching how
    ``_pubsub_queue_keys_by_base`` scans once for every ``rt_api.*`` key) are
    driven from ``list_lengths``, so every key supplied is treated as if it
    already exists in the fake keyspace.
    """
    rc = MagicMock()

    rc.llen.side_effect = lambda key: list_lengths.get(key, 0)
    rc.scan_iter.side_effect = lambda match, count=None, **kwargs: iter(list(list_lengths.keys()))
    return rc


class TestPubsubQueueKeysByBase:
    EMIT_KEY = queue_name_for("emit_handler").encode()

    def test_groups_bare_and_priority_suffixed_keys_under_common_base(self) -> None:
        priority_key = self.EMIT_KEY + tasks.KOMBU_SEP + b"3"
        rc = _make_pubsub_redis_mock({self.EMIT_KEY: 5, priority_key: 50})

        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)

        assert set(keys_by_base[queue_name_for("emit_handler")]) == {self.EMIT_KEY, priority_key}

    def test_ignores_keys_for_unknown_queue_names(self) -> None:
        unrelated_key = b"rt_api.some_other_unrelated_queue"
        rc = _make_pubsub_redis_mock({self.EMIT_KEY: 5, unrelated_key: 5})

        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)

        assert unrelated_key not in {key for keys in keys_by_base.values() for key in keys}

    def test_scans_the_pubsub_db_exactly_once(self) -> None:
        rc = _make_pubsub_redis_mock({self.EMIT_KEY: 5})

        tasks._pubsub_queue_keys_by_base(rc)

        rc.scan_iter.assert_called_once()


class TestTrimRtPubsubQueues:
    EMIT_KEY = queue_name_for("emit_handler").encode()

    def test_trims_queue_longer_than_max_keeping_head(
        self, monkeypatch: pytest.MonkeyPatch, settings, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings.RT_PUBSUB_QUEUE_MAX_LENGTH = 100
        rc = _make_pubsub_redis_mock({self.EMIT_KEY: 1000})
        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)

        increments: list[tuple[str, int, Any]] = []
        monkeypatch.setattr(
            tasks, "increment", lambda metric, value=1, tags=None, **kw: increments.append((metric, value, tags))
        )

        with caplog.at_level(logging.WARNING, logger="rt_api.tasks"):
            tasks._trim_rt_pubsub_queues(rc, keys_by_base)

        # Keep the newest messages: head range [0, max-1]. Kombu LPUSHes at the
        # head, so the head holds the newest entries.
        rc.ltrim.assert_any_call(self.EMIT_KEY, 0, 99)
        assert any("Trimmed rt_api pub/sub queue" in r.message for r in caplog.records)
        trim_metrics = [m for m in increments if m[0] == "rt_pubsub_queue_trimmed"]
        assert ("rt_pubsub_queue_trimmed", 900, [f"queue:{queue_name_for('emit_handler')}"]) in trim_metrics

    def test_does_not_trim_queue_at_or_under_max(self, monkeypatch: pytest.MonkeyPatch, settings) -> None:
        settings.RT_PUBSUB_QUEUE_MAX_LENGTH = 100
        rc = _make_pubsub_redis_mock({self.EMIT_KEY: 100})
        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)
        monkeypatch.setattr(tasks, "increment", lambda *a, **k: None)

        tasks._trim_rt_pubsub_queues(rc, keys_by_base)

        rc.ltrim.assert_not_called()

    def test_disabled_when_max_length_non_positive(self, settings) -> None:
        settings.RT_PUBSUB_QUEUE_MAX_LENGTH = 0
        rc = _make_pubsub_redis_mock({self.EMIT_KEY: 50_000})
        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)

        tasks._trim_rt_pubsub_queues(rc, keys_by_base)

        rc.ltrim.assert_not_called()

    def test_trims_priority_suffixed_keys_too(self, monkeypatch: pytest.MonkeyPatch, settings) -> None:
        settings.RT_PUBSUB_QUEUE_MAX_LENGTH = 10
        base = self.EMIT_KEY
        priority_key = base + tasks.KOMBU_SEP + b"3"
        rc = _make_pubsub_redis_mock({base: 5, priority_key: 50})
        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)
        monkeypatch.setattr(tasks, "increment", lambda *a, **k: None)

        tasks._trim_rt_pubsub_queues(rc, keys_by_base)

        # base (5) under max -> not trimmed; priority key (50) over max -> trimmed.
        rc.ltrim.assert_called_once_with(priority_key, 0, 9)


class TestGaugeRtPubsubQueueLengths:
    def test_gauges_every_queue(self, monkeypatch: pytest.MonkeyPatch) -> None:
        lengths = {name.encode(): idx * 10 for idx, name in enumerate(all_queue_names())}
        rc = _make_pubsub_redis_mock(lengths)
        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)

        gauges: list[tuple[str, int, Any]] = []
        monkeypatch.setattr(
            tasks, "update_gauge", lambda metric, value, tags=None, **kw: gauges.append((metric, value, tags))
        )

        tasks._gauge_rt_pubsub_queue_lengths(rc, keys_by_base)

        gauged_queues = {tags[0] for _, _, tags in gauges}
        expected_queues = {f"queue:{name}" for name in all_queue_names()}
        assert gauged_queues == expected_queues
        assert all(metric == "rt_pubsub_queue_length" for metric, _, _ in gauges)

    def test_gauges_zero_for_queue_with_no_keys_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An empty keyspace still yields a zero-length gauge for every known
        # queue name, not just the ones with a key currently in Redis.
        rc = _make_pubsub_redis_mock({})
        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)
        assert keys_by_base == {}

        gauges: list[tuple[str, int, Any]] = []
        monkeypatch.setattr(
            tasks, "update_gauge", lambda metric, value, tags=None, **kw: gauges.append((metric, value, tags))
        )

        tasks._gauge_rt_pubsub_queue_lengths(rc, keys_by_base)

        assert all(value == 0 for _, value, _ in gauges)
        gauged_queues = {tags[0] for _, _, tags in gauges}
        assert gauged_queues == {f"queue:{name}" for name in all_queue_names()}


class TestGaugeAndTrimShareOneScan:
    def test_full_gauge_and_trim_run_scans_pubsub_db_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch, settings
    ) -> None:
        settings.RT_PUBSUB_QUEUE_MAX_LENGTH = 100
        emit_key = queue_name_for("emit_handler").encode()
        rc = _make_pubsub_redis_mock({emit_key: 1000})
        monkeypatch.setattr(tasks, "update_gauge", lambda *a, **k: None)
        monkeypatch.setattr(tasks, "increment", lambda *a, **k: None)

        keys_by_base = tasks._pubsub_queue_keys_by_base(rc)
        tasks._gauge_rt_pubsub_queue_lengths(rc, keys_by_base)
        tasks._trim_rt_pubsub_queues(rc, keys_by_base)

        rc.scan_iter.assert_called_once()
