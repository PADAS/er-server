from __future__ import annotations

import logging
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest
from celery import states as celery_states
from celery.result import EagerResult

from rt_api.client import (
    PENDING_SOURCE_OBS_DOMAINS_KEY,
    PENDING_SOURCE_OBSERVATIONS_KEY,
    add_pending_source_observation,
    drain_pending_source_observations,
    get_pending_source_obs_domains,
    redis_client,
    remove_drained_source_observations,
    remove_pending_source_obs_domain_if_empty,
)
from rt_api.tasks import coordinate_pending_source_obs_drain as coordinator_task
from rt_api.tasks import drain_pending_source_observations as drain_task


class TestPendingSourceObsClientFunctions:
    TEST_DOMAIN = "test-pending-obs.example.com"

    def setup_method(self) -> None:
        key = PENDING_SOURCE_OBSERVATIONS_KEY.format(self.TEST_DOMAIN)
        redis_client.delete(key)
        redis_client.srem(PENDING_SOURCE_OBS_DOMAINS_KEY, self.TEST_DOMAIN)

    def teardown_method(self) -> None:
        key = PENDING_SOURCE_OBSERVATIONS_KEY.format(self.TEST_DOMAIN)
        redis_client.delete(key)
        redis_client.srem(PENDING_SOURCE_OBS_DOMAINS_KEY, self.TEST_DOMAIN)

    def test_add_adds_source_id_to_tenant_scoped_set(self) -> None:
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")

        key = PENDING_SOURCE_OBSERVATIONS_KEY.format(self.TEST_DOMAIN)
        members = redis_client.smembers(key)
        assert b"src-1" in members

    def test_drain_returns_accumulated_ids_without_clearing_set(self) -> None:
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")
        add_pending_source_observation(self.TEST_DOMAIN, "src-2")

        result = drain_pending_source_observations(self.TEST_DOMAIN)

        assert b"src-1" in result
        assert b"src-2" in result

        # drain no longer deletes — the caller must call remove_drained_source_observations
        key = PENDING_SOURCE_OBSERVATIONS_KEY.format(self.TEST_DOMAIN)
        assert redis_client.scard(key) == 2

    def test_drain_empty_set_returns_empty(self) -> None:
        result = drain_pending_source_observations(self.TEST_DOMAIN)

        assert result == set()

    def test_drain_does_nothing_when_domain_is_none(self) -> None:
        with patch("rt_api.client.redis_client") as mock_redis:
            result = drain_pending_source_observations(None)
        mock_redis.smembers.assert_not_called()
        assert result == set()

    def test_drain_does_nothing_when_domain_is_empty_string(self) -> None:
        with patch("rt_api.client.redis_client") as mock_redis:
            result = drain_pending_source_observations("")
        mock_redis.smembers.assert_not_called()
        assert result == set()

    def test_add_does_not_write_when_domain_is_none(self) -> None:
        with patch("rt_api.client.redis_client") as mock_redis:
            add_pending_source_observation(None, "src-1")
        mock_redis.sadd.assert_not_called()

    def test_add_does_not_write_when_domain_is_empty_string(self) -> None:
        with patch("rt_api.client.redis_client") as mock_redis:
            add_pending_source_observation("", "src-1")
        mock_redis.sadd.assert_not_called()

    def test_remove_drained_removes_only_dispatched_ids(self) -> None:
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")
        add_pending_source_observation(self.TEST_DOMAIN, "src-2")
        add_pending_source_observation(self.TEST_DOMAIN, "src-3")

        remove_drained_source_observations(self.TEST_DOMAIN, {b"src-1", b"src-2"})

        key = PENDING_SOURCE_OBSERVATIONS_KEY.format(self.TEST_DOMAIN)
        remaining = redis_client.smembers(key)
        assert remaining == {b"src-3"}

    def test_remove_drained_is_noop_for_empty_set(self) -> None:
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")

        with patch("rt_api.client.redis_client") as mock_redis:
            remove_drained_source_observations(self.TEST_DOMAIN, set())
        mock_redis.srem.assert_not_called()

    def test_remove_drained_does_not_write_when_domain_is_none(self) -> None:
        with patch("rt_api.client.redis_client") as mock_redis:
            remove_drained_source_observations(None, {b"src-1"})
        mock_redis.srem.assert_not_called()

    def test_concurrent_addition_survives_drain_cycle(self) -> None:
        """Id added after SMEMBERS but before SREM must not be lost."""
        add_pending_source_observation(self.TEST_DOMAIN, "src-before")

        # Simulate a concurrent write happening while the drain is in progress.
        drained = drain_pending_source_observations(self.TEST_DOMAIN)
        add_pending_source_observation(self.TEST_DOMAIN, "src-concurrent")
        remove_drained_source_observations(self.TEST_DOMAIN, drained)

        key = PENDING_SOURCE_OBSERVATIONS_KEY.format(self.TEST_DOMAIN)
        remaining = redis_client.smembers(key)
        assert b"src-concurrent" in remaining
        assert b"src-before" not in remaining

    def test_add_registers_domain_in_dirty_registry(self) -> None:
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")

        members = redis_client.smembers(PENDING_SOURCE_OBS_DOMAINS_KEY)
        assert self.TEST_DOMAIN.encode() in members

    def test_get_pending_source_obs_domains_returns_registered_domain(self) -> None:
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")

        domains = get_pending_source_obs_domains()
        assert self.TEST_DOMAIN in domains

    def test_get_pending_source_obs_domains_returns_empty_when_none_registered(self) -> None:
        domains = get_pending_source_obs_domains()
        assert self.TEST_DOMAIN not in domains

    def test_remove_domain_if_empty_removes_domain_when_pending_set_is_empty(self) -> None:
        # Register the domain then drain the pending set.
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")
        remove_drained_source_observations(self.TEST_DOMAIN, {b"src-1"})

        remove_pending_source_obs_domain_if_empty(self.TEST_DOMAIN)

        members = redis_client.smembers(PENDING_SOURCE_OBS_DOMAINS_KEY)
        assert self.TEST_DOMAIN.encode() not in members

    def test_remove_domain_if_empty_leaves_domain_when_pending_set_has_items(self) -> None:
        # Register domain with two items, drain only one.
        add_pending_source_observation(self.TEST_DOMAIN, "src-1")
        add_pending_source_observation(self.TEST_DOMAIN, "src-2")
        remove_drained_source_observations(self.TEST_DOMAIN, {b"src-1"})

        remove_pending_source_obs_domain_if_empty(self.TEST_DOMAIN)

        members = redis_client.smembers(PENDING_SOURCE_OBS_DOMAINS_KEY)
        assert self.TEST_DOMAIN.encode() in members

    def test_remove_domain_if_empty_mid_cycle_arrival_keeps_domain_registered(self) -> None:
        """Domain stays registered when a new id arrives after SMEMBERS but
        before registry cleanup — the next beat cycle will re-drain it."""
        add_pending_source_observation(self.TEST_DOMAIN, "src-before")

        drained = drain_pending_source_observations(self.TEST_DOMAIN)
        # Simulate concurrent arrival after SMEMBERS.
        add_pending_source_observation(self.TEST_DOMAIN, "src-concurrent")
        remove_drained_source_observations(self.TEST_DOMAIN, drained)

        remove_pending_source_obs_domain_if_empty(self.TEST_DOMAIN)

        # Domain must remain registered because the pending set is not empty.
        members = redis_client.smembers(PENDING_SOURCE_OBS_DOMAINS_KEY)
        assert self.TEST_DOMAIN.encode() in members


class _StopLoop(BaseException):
    """Break the supervision loop's while-True without being caught by except Exception."""


@pytest.fixture
def new_observation_handler(monkeypatch) -> Callable:
    """Extract the new_observation_handler closure from pubsub_listener.start()."""
    from rt_api import pubsub_listener

    captured: list[dict] = []

    def fake_subscribe(subscriptions):
        # Capture subscriptions on the first call, then raise a BaseException
        # sentinel so the supervision loop's `except Exception` does NOT catch
        # it and the thread target exits promptly.  Without this, the while-True
        # loop would never return and the fixture would hang.
        captured.extend(subscriptions)
        raise _StopLoop

    monkeypatch.setattr("rt_api.pubsub_listener.pubsub.subscribe_without_retry", fake_subscribe)
    monkeypatch.setattr("rt_api.pubsub_listener.time.sleep", lambda _: None)
    monkeypatch.setattr("rt_api.pubsub_listener.stats.increment", lambda *a, **kw: None)

    captured_threads: list[dict] = []

    class FakeThread:
        def __init__(self, target=None, name=None, args=()):  # noqa: ANN001
            captured_threads.append({"target": target, "args": args})

        def start(self) -> None:
            pass

    monkeypatch.setattr("rt_api.pubsub_listener.Thread", FakeThread)
    pubsub_listener.start(MagicMock())

    # Drive one thread target so fake_subscribe is called and subscriptions are
    # captured.  _StopLoop (BaseException) breaks the supervision loop cleanly.
    assert captured_threads, "No Thread was constructed"
    target = captured_threads[0]["target"]
    args = captured_threads[0]["args"]
    with pytest.raises(_StopLoop):
        target(*args)

    handler = next(
        (s["callback"] for s in captured if s["callback"].__name__ == "new_observation_handler"),
        None,
    )
    assert handler is not None, "new_observation_handler not found in subscriptions"
    return handler


class TestNewObservationHandlerAccumulates:
    def test_accumulates_source_id_instead_of_dispatching(self, monkeypatch, new_observation_handler: Callable) -> None:
        mock_add = MagicMock()
        monkeypatch.setattr("rt_api.pubsub_listener.client.add_pending_source_observation", mock_add)

        new_observation_handler({"source_id": "src-1", "domain": "testdomain"}, None)

        mock_add.assert_called_once_with("testdomain", "src-1")

    def test_does_not_call_handle_new_source_observation_apply_async(
        self, monkeypatch, new_observation_handler: Callable
    ) -> None:
        monkeypatch.setattr("rt_api.pubsub_listener.client.add_pending_source_observation", MagicMock())

        with patch("rt_api.tasks.handle_new_source_observation") as mock_task:
            new_observation_handler({"source_id": "src-1", "domain": "testdomain"}, None)

        mock_task.apply_async.assert_not_called()

    def test_drops_observation_and_warns_when_domain_is_absent(
        self, monkeypatch, caplog, new_observation_handler: Callable
    ) -> None:
        mock_add = MagicMock()
        monkeypatch.setattr("rt_api.pubsub_listener.client.add_pending_source_observation", mock_add)
        with caplog.at_level(logging.WARNING, logger="rt_api.pubsub_listener"):
            new_observation_handler({"source_id": "src-no-domain"}, None)
        mock_add.assert_not_called()
        assert any("dropping" in r.message for r in caplog.records)


class TestDrainPendingSourceObservationsTask:
    def _patch_registry_cleanup(self, monkeypatch) -> MagicMock:
        mock = MagicMock()
        monkeypatch.setattr("rt_api.tasks.client.remove_pending_source_obs_domain_if_empty", mock)
        return mock

    def test_dispatches_handle_new_source_observation_for_each_drained_id(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value={b"src-1", b"src-2"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            MagicMock(),
        )
        self._patch_registry_cleanup(monkeypatch)

        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        with patch("rt_api.tasks.handle_new_source_observation") as mock_handle:
            drain_task.run()

        assert mock_handle.apply_async.call_count == 2
        dispatched_source_ids = {c.kwargs["args"][0] for c in mock_handle.apply_async.call_args_list}
        assert dispatched_source_ids == {"src-1", "src-2"}

    def test_dispatches_each_source_id_as_positional_arg(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value={b"src-abc"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            MagicMock(),
        )
        self._patch_registry_cleanup(monkeypatch)

        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        with patch("rt_api.tasks.handle_new_source_observation") as mock_handle:
            drain_task.run()

        mock_handle.apply_async.assert_called_once_with(args=("src-abc",), kwargs={"domain": "testdomain"})

    def test_dispatches_with_domain_kwarg(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value={b"src-abc"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            MagicMock(),
        )
        self._patch_registry_cleanup(monkeypatch)
        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        with patch("rt_api.tasks.handle_new_source_observation") as mock_handle:
            drain_task.run()

        mock_handle.apply_async.assert_called_once_with(
            args=("src-abc",),
            kwargs={"domain": "testdomain"},
        )

    def test_empty_drain_dispatches_nothing(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value=set()),
        )
        mock_remove = MagicMock()
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            mock_remove,
        )
        self._patch_registry_cleanup(monkeypatch)

        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        with patch("rt_api.tasks.handle_new_source_observation") as mock_handle:
            drain_task.run()

        mock_handle.apply_async.assert_not_called()
        # remove_drained_source_observations is called with empty set; it is a noop
        mock_remove.assert_called_once_with("testdomain", set())

    def test_srem_called_only_for_dispatched_ids(self, monkeypatch) -> None:
        """Only the ids that were successfully dispatched are removed from Redis."""
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value={b"src-1", b"src-2"}),
        )
        mock_remove = MagicMock()
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            mock_remove,
        )
        self._patch_registry_cleanup(monkeypatch)
        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        with patch("rt_api.tasks.handle_new_source_observation"):
            drain_task.run()

        mock_remove.assert_called_once()
        _domain, dispatched = mock_remove.call_args.args
        assert _domain == "testdomain"
        assert dispatched == {b"src-1", b"src-2"}

    def test_rejected_source_id_is_not_removed_from_pending_set(self, monkeypatch) -> None:
        """Source ids whose apply_async is gracefully suppressed (REJECTED) must
        not be passed to remove_drained_source_observations.  They stay in the
        pending Redis set so the next drain cycle retries them once the
        celery-once lock clears."""
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value={b"src-ok", b"src-locked"}),
        )
        mock_remove = MagicMock()
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            mock_remove,
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_pending_source_obs_domain_if_empty",
            MagicMock(),
        )
        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        ok_result = MagicMock()
        ok_result.state = celery_states.SUCCESS
        rejected_result = EagerResult(None, None, celery_states.REJECTED)

        def side_effect_apply_async(args=(), kwargs=None, **_opts) -> MagicMock | EagerResult:
            source_id = args[0] if args else None
            return rejected_result if source_id == "src-locked" else ok_result

        with patch("rt_api.tasks.handle_new_source_observation") as mock_handle:
            mock_handle.apply_async.side_effect = side_effect_apply_async
            drain_task.run()

        mock_remove.assert_called_once()
        _domain, dispatched = mock_remove.call_args.args
        assert _domain == "testdomain"
        # src-ok was enqueued — it must be removed from the pending set
        assert b"src-ok" in dispatched
        # src-locked was suppressed by celery-once — it must NOT be removed so
        # the next drain cycle retries it
        assert b"src-locked" not in dispatched

    def test_drain_task_calls_registry_cleanup_after_srem(self, monkeypatch) -> None:
        """After removing dispatched ids, the drain task must attempt to remove
        the domain from the dirty registry (conditionally on empty pending set)."""
        monkeypatch.setattr(
            "rt_api.tasks.client.drain_pending_source_observations",
            MagicMock(return_value={b"src-1"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_drained_source_observations",
            MagicMock(),
        )
        mock_registry_cleanup = MagicMock()
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_pending_source_obs_domain_if_empty",
            mock_registry_cleanup,
        )
        mock_tenant = MagicMock()
        mock_tenant.domain = "testdomain"
        monkeypatch.setattr("rt_api.tasks.get_tenant_settings", MagicMock(return_value=mock_tenant))

        with patch("rt_api.tasks.handle_new_source_observation"):
            drain_task.run()

        mock_registry_cleanup.assert_called_once_with("testdomain")


class TestCheckOrphanedPendingSourceObsSets:
    def test_logs_warning_for_orphaned_domain(self, monkeypatch, caplog) -> None:
        from rt_api.tasks import _check_orphaned_pending_source_obs_sets

        monkeypatch.setattr(
            "rt_api.tasks.get_current_cluster_domains",
            MagicMock(return_value={"known.example.com"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.redis_client",
            MagicMock(
                scan_iter=MagicMock(return_value=[b"rt_api:pending_source_obs:orphaned.example.com"]),
                scard=MagicMock(return_value=3),
            ),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value=set()),
        )
        mock_gauge = MagicMock()
        monkeypatch.setattr("rt_api.tasks.update_gauge", mock_gauge)

        with caplog.at_level(logging.WARNING, logger="rt_api.tasks"):
            _check_orphaned_pending_source_obs_sets()

        assert any("orphaned.example.com" in r.message for r in caplog.records)
        mock_gauge.assert_any_call(metric="rt_api_orphaned_pending_source_obs_sets", value=1)

    def test_no_warning_for_known_domains(self, monkeypatch, caplog) -> None:
        from rt_api.tasks import _check_orphaned_pending_source_obs_sets

        monkeypatch.setattr(
            "rt_api.tasks.get_current_cluster_domains",
            MagicMock(return_value={"known.example.com"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.redis_client",
            MagicMock(
                scan_iter=MagicMock(return_value=[b"rt_api:pending_source_obs:known.example.com"]),
                scard=MagicMock(return_value=0),
            ),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value=set()),
        )
        mock_gauge = MagicMock()
        monkeypatch.setattr("rt_api.tasks.update_gauge", mock_gauge)

        with caplog.at_level(logging.WARNING, logger="rt_api.tasks"):
            _check_orphaned_pending_source_obs_sets()

        assert not any("orphaned" in r.message for r in caplog.records)
        mock_gauge.assert_any_call(metric="rt_api_orphaned_pending_source_obs_sets", value=0)

    def test_zero_gauge_when_no_pending_sets_exist(self, monkeypatch) -> None:
        from rt_api.tasks import _check_orphaned_pending_source_obs_sets

        monkeypatch.setattr(
            "rt_api.tasks.get_current_cluster_domains",
            MagicMock(return_value={"known.example.com"}),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.redis_client",
            MagicMock(
                scan_iter=MagicMock(return_value=[]),
                scard=MagicMock(return_value=0),
            ),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value=set()),
        )
        mock_gauge = MagicMock()
        monkeypatch.setattr("rt_api.tasks.update_gauge", mock_gauge)

        _check_orphaned_pending_source_obs_sets()

        mock_gauge.assert_any_call(metric="rt_api_orphaned_pending_source_obs_sets", value=0)

    def test_emits_pending_depth_gauge_with_summed_scard(self, monkeypatch) -> None:
        from rt_api.tasks import _check_orphaned_pending_source_obs_sets

        monkeypatch.setattr(
            "rt_api.tasks.get_current_cluster_domains",
            MagicMock(return_value={"a.example.com", "b.example.com"}),
        )
        # Two known-domain sets with 4 and 7 pending IDs respectively.
        keys = [
            b"rt_api:pending_source_obs:a.example.com",
            b"rt_api:pending_source_obs:b.example.com",
        ]
        scard_values = {keys[0]: 4, keys[1]: 7}
        monkeypatch.setattr(
            "rt_api.tasks.client.redis_client",
            MagicMock(
                scan_iter=MagicMock(return_value=keys),
                scard=MagicMock(side_effect=lambda k: scard_values[k]),
            ),
        )
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value=set()),
        )
        mock_gauge = MagicMock()
        monkeypatch.setattr("rt_api.tasks.update_gauge", mock_gauge)

        _check_orphaned_pending_source_obs_sets()

        mock_gauge.assert_any_call(metric="rt_api_pending_source_obs_depth", value=11)

    def test_removes_stale_registry_entry_for_empty_pending_set(self, monkeypatch) -> None:
        """Registry entries for domains whose pending set is empty/missing are
        cleaned up by the orphan sweep."""
        from rt_api.tasks import _check_orphaned_pending_source_obs_sets

        monkeypatch.setattr(
            "rt_api.tasks.get_current_cluster_domains",
            MagicMock(return_value={"known.example.com"}),
        )
        # No pending sets visible on the scan.
        monkeypatch.setattr(
            "rt_api.tasks.client.redis_client",
            MagicMock(
                scan_iter=MagicMock(return_value=[]),
                scard=MagicMock(return_value=0),
            ),
        )
        # Registry still has a stale entry (crash between SREM-dispatched and cleanup).
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value={"stale.example.com"}),
        )
        mock_remove = MagicMock()
        monkeypatch.setattr(
            "rt_api.tasks.client.remove_pending_source_obs_domain_if_empty",
            mock_remove,
        )
        monkeypatch.setattr("rt_api.tasks.update_gauge", MagicMock())

        _check_orphaned_pending_source_obs_sets()

        mock_remove.assert_called_once_with("stale.example.com")


class TestCoordinatePendingSourceObsDrain:
    def test_dispatches_drain_only_for_dirty_domains(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value={"dirty.example.com", "also-dirty.example.com"}),
        )

        with patch("rt_api.tasks.drain_pending_source_observations") as mock_drain:
            coordinator_task.run()

        assert mock_drain.apply_async.call_count == 2
        dispatched_domains = {c.kwargs["kwargs"]["tenant_domain"] for c in mock_drain.apply_async.call_args_list}
        assert dispatched_domains == {"dirty.example.com", "also-dirty.example.com"}

    def test_does_not_dispatch_when_no_dirty_domains(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value=set()),
        )

        with patch("rt_api.tasks.drain_pending_source_observations") as mock_drain:
            coordinator_task.run()

        mock_drain.apply_async.assert_not_called()

    def test_dispatches_with_expires_matching_drain_interval(self, monkeypatch) -> None:
        from django.conf import settings

        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value={"d.example.com"}),
        )

        with patch("rt_api.tasks.drain_pending_source_observations") as mock_drain:
            coordinator_task.run()

        call_kwargs = mock_drain.apply_async.call_args.kwargs
        assert call_kwargs["expires"] == settings.REALTIME_OBS_DRAIN_INTERVAL_SECONDS

    def test_dispatches_tenant_domain_kwarg_to_drain_task(self, monkeypatch) -> None:
        """OverAllTenantTask uses 'tenant_domain' kwarg to run in per-tenant context."""
        monkeypatch.setattr(
            "rt_api.tasks.client.get_pending_source_obs_domains",
            MagicMock(return_value={"one.example.com"}),
        )

        with patch("rt_api.tasks.drain_pending_source_observations") as mock_drain:
            coordinator_task.run()

        mock_drain.apply_async.assert_called_once_with(
            kwargs={"tenant_domain": "one.example.com"},
            expires=mock_drain.apply_async.call_args.kwargs["expires"],
        )


class TestCeleryQueueAssignments:
    def test_coordinator_routes_to_realtime_p2(self) -> None:
        from das_server.celery import app

        routes = app.conf.task_routes
        assert routes["rt_api.tasks.coordinate_pending_source_obs_drain"]["queue"] == "realtime_p2"

    def test_drain_routes_to_realtime_p2(self) -> None:
        from das_server.celery import app

        routes = app.conf.task_routes
        assert routes["rt_api.tasks.drain_pending_source_observations"]["queue"] == "realtime_p2"

    def test_handle_new_source_observation_routes_to_realtime_p3(self) -> None:
        from das_server.celery import app

        routes = app.conf.task_routes
        assert routes["rt_api.tasks.handle_new_source_observation"]["queue"] == "realtime_p3"

    def test_drain_beat_entry_uses_coordinator_task(self) -> None:
        from das_server.celery import app

        entry = app.conf.beat_schedule["drain-pending-source-observations"]
        assert entry["task"] == "rt_api.tasks.coordinate_pending_source_obs_drain"

    def test_drain_beat_entry_schedule_and_expires(self) -> None:
        from datetime import timedelta

        from django.conf import settings

        from das_server.celery import app

        interval = settings.REALTIME_OBS_DRAIN_INTERVAL_SECONDS
        entry = app.conf.beat_schedule["drain-pending-source-observations"]
        assert entry["schedule"] == timedelta(seconds=interval)
        assert entry["options"]["expires"] == interval
