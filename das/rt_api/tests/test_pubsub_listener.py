from __future__ import annotations

import logging
from types import CodeType
from typing import Any
from unittest.mock import MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from das_server.pubsub import swallow_callback_exceptions
from rt_api import pubsub_listener
from rt_api.pubsub_subscriptions import SUBSCRIPTIONS, all_queue_names, queue_name_for


class TestSwallowCallbackExceptions:
    def test_returns_callback_result_on_success(self) -> None:
        callback = MagicMock(return_value="ok")
        wrapped = swallow_callback_exceptions(callback, "das.realtime.emit")

        result = wrapped({"a": 1}, "message")

        assert result == "ok"
        callback.assert_called_once_with({"a": 1}, "message")

    def test_swallows_and_logs_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        def boom(data: Any, message: Any) -> None:
            raise KeyError("missing field")

        wrapped = swallow_callback_exceptions(boom, "das.realtime.emit")

        with caplog.at_level(logging.ERROR, logger="das_server.pubsub"):
            result = wrapped({}, None)

        assert result is None
        assert "Unhandled exception in pub/sub callback" in caplog.text
        assert "das.realtime.emit" in caplog.text

    def test_subsequent_messages_still_processed_after_poison_message(self) -> None:
        calls: list[Any] = []

        def handler(data: Any, message: Any) -> None:
            if data == "poison":
                raise ValueError("poison message")
            calls.append(data)

        wrapped = swallow_callback_exceptions(handler, "das.event.new")

        wrapped("good-1", None)
        wrapped("poison", None)  # must not propagate
        wrapped("good-2", None)

        assert calls == ["good-1", "good-2"]


class _StopLoop(BaseException):
    """Sentinel to break the supervision loop's while-True in tests.

    Must subclass BaseException (not Exception) so the loop's `except Exception`
    does NOT catch it — otherwise it would be treated as a restartable failure
    and the loop would spin forever.
    """


class TestSupervisionLoop:
    def _capture_listener_target(self, monkeypatch: pytest.MonkeyPatch):
        """Start() spawns threads; capture the thread target without running it."""
        captured: dict[str, Any] = {}

        class FakeThread:
            def __init__(self, target=None, name=None, args=()):  # noqa: ANN001
                captured.setdefault("target", target)
                captured.setdefault("args", args)

            def start(self) -> None:
                # Do not run the supervision loop on a real thread.
                pass

        monkeypatch.setattr(pubsub_listener, "Thread", FakeThread)
        pubsub_listener.start(realtime_server=MagicMock())
        return captured["target"], captured["args"]

    def test_restart_after_exception_calls_subscribe_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        target, args = self._capture_listener_target(monkeypatch)

        call_count = {"n": 0}

        def fake_subscribe(subscriptions):  # noqa: ANN001
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("broker died")
            # Second invocation: break out of the while-True supervision loop.
            raise _StopLoop

        sleep_calls: list[float] = []
        increments: list[tuple[str, Any]] = []

        monkeypatch.setattr(pubsub_listener.pubsub, "subscribe_without_retry", fake_subscribe)
        monkeypatch.setattr(pubsub_listener.time, "sleep", lambda d: sleep_calls.append(d))
        monkeypatch.setattr(
            pubsub_listener.stats,
            "increment",
            lambda metric, tags=None, **kw: increments.append((metric, tags)),
        )

        with pytest.raises(_StopLoop):
            target(*args)

        # subscribe was retried after the first exception.
        assert call_count["n"] == 2
        # restart metric emitted once (after the first failure, before retry).
        assert increments[0][0] == "rt_pubsub_listener_restart"
        assert any("reason:exception" in t for t in increments[0][1])
        # the configured delay was used (no real sleep).
        assert sleep_calls == [pubsub_listener.LISTENER_RESTART_DELAY_SECONDS]

    def test_restart_after_graceful_return(self, monkeypatch: pytest.MonkeyPatch) -> None:
        target, args = self._capture_listener_target(monkeypatch)

        call_count = {"n": 0}

        def fake_subscribe(subscriptions):  # noqa: ANN001
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # graceful return -> should restart
            raise _StopLoop

        increments: list[tuple[str, Any]] = []
        monkeypatch.setattr(pubsub_listener.pubsub, "subscribe_without_retry", fake_subscribe)
        monkeypatch.setattr(pubsub_listener.time, "sleep", lambda d: None)
        monkeypatch.setattr(
            pubsub_listener.stats,
            "increment",
            lambda metric, tags=None, **kw: increments.append((metric, tags)),
        )

        with pytest.raises(_StopLoop):
            target(*args)

        assert call_count["n"] == 2
        assert increments[0][0] == "rt_pubsub_listener_restart"
        assert any("reason:returned" in t for t in increments[0][1])

    def test_redis_connection_error_restarts_the_listener_with_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A broker connection failure must reach this loop, not be retried inside subscribe.

        ``das_server.pubsub.subscribe`` is wrapped in
        ``@retry_on_exception(ConnectionError, retry_forever=True, delay=1)``, so
        calling it here would swallow the most common broker failure mode: the
        restart metric would never increment and the 5s backoff would never
        apply. The loop therefore calls the undecorated ``subscribe_without_retry``
        and owns retry, backoff and metrics for every exception type.
        """
        target, args = self._capture_listener_target(monkeypatch)

        call_count = {"n": 0}

        def fake_subscribe_without_retry(subscriptions):  # noqa: ANN001
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RedisConnectionError("Error 111 connecting to redis:6379. Connection refused.")
            raise _StopLoop

        def retry_wrapped_subscribe(subscriptions):  # noqa: ANN001
            raise AssertionError("supervision loop must not call the retry-wrapped pubsub.subscribe")

        sleep_calls: list[float] = []
        increments: list[tuple[str, Any]] = []

        monkeypatch.setattr(pubsub_listener.pubsub, "subscribe_without_retry", fake_subscribe_without_retry)
        monkeypatch.setattr(pubsub_listener.pubsub, "subscribe", retry_wrapped_subscribe)
        monkeypatch.setattr(pubsub_listener.time, "sleep", lambda d: sleep_calls.append(d))
        monkeypatch.setattr(
            pubsub_listener.stats,
            "increment",
            lambda metric, tags=None, **kw: increments.append((metric, tags)),
        )

        with pytest.raises(_StopLoop):
            target(*args)

        assert call_count["n"] == 2
        assert increments[0][0] == "rt_pubsub_listener_restart"
        assert any("reason:exception" in t for t in increments[0][1])
        assert sleep_calls == [pubsub_listener.LISTENER_RESTART_DELAY_SECONDS]

    def test_subscriptions_are_built_once_per_thread_not_once_per_restart(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The subscription list is built once per thread and reused on restart.

        Rebuilding per attempt re-logged one 'Adding subscription' line per
        routing key, so a prolonged broker outage logged len(SUBSCRIPTIONS) x 5
        threads every LISTENER_RESTART_DELAY_SECONDS. Reuse is safe because the
        list holds only strings and stateless wrapper callables — kombu builds
        its Queue/Consumer objects fresh inside subscribe on every attempt.
        """
        target, args = self._capture_listener_target(monkeypatch)

        recorded: list[Any] = []

        def fake_subscribe_without_retry(subscriptions):  # noqa: ANN001
            recorded.append(subscriptions)
            if len(recorded) < 3:
                raise RuntimeError("broker died")
            raise _StopLoop

        monkeypatch.setattr(pubsub_listener.pubsub, "subscribe_without_retry", fake_subscribe_without_retry)
        monkeypatch.setattr(pubsub_listener.time, "sleep", lambda d: None)
        monkeypatch.setattr(pubsub_listener.stats, "increment", lambda *a, **k: None)

        with caplog.at_level(logging.INFO, logger="rt_api.pubsub_listener"):
            with pytest.raises(_StopLoop):
                target(*args)

        # Three attempts, every one handed the identical list object.
        assert len(recorded) == 3
        assert all(attempt is recorded[0] for attempt in recorded)

        built_log_lines = [r for r in caplog.records if r.getMessage().startswith("Adding subscription")]
        assert len(built_log_lines) == len(SUBSCRIPTIONS)


def _handler_closure_names() -> set[str]:
    """Names of the ``*_handler`` closures defined inside ``pubsub_listener.start``.

    Read off ``start``'s code object because the closures are function locals:
    there is no other way to see a handler that exists but was never wired into
    a subscription.
    """
    return {
        const.co_name
        for const in pubsub_listener.start.__code__.co_consts
        if isinstance(const, CodeType) and const.co_name.endswith("_handler")
    }


class TestSubscriptionTableMatchesRegisteredSubscriptions:
    def test_built_subscriptions_match_canonical_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards against drift between pubsub_subscriptions.SUBSCRIPTIONS and the
        handler closures that pubsub_listener.start actually registers."""
        captured_subscriptions: dict[str, Any] = {}

        class FakeThread:
            def __init__(self, target=None, name=None, args=()):  # noqa: ANN001
                captured_subscriptions.setdefault("target", target)
                captured_subscriptions.setdefault("args", args)

            def start(self) -> None:
                pass

        recorded: list[dict[str, Any]] = []

        def fake_subscribe(subscriptions):  # noqa: ANN001
            recorded.extend(subscriptions)
            raise _StopLoop  # break the supervision loop after first build

        monkeypatch.setattr(pubsub_listener, "Thread", FakeThread)
        monkeypatch.setattr(pubsub_listener.pubsub, "subscribe_without_retry", fake_subscribe)
        monkeypatch.setattr(pubsub_listener.time, "sleep", lambda d: None)
        monkeypatch.setattr(pubsub_listener.stats, "increment", lambda *a, **k: None)

        pubsub_listener.start(realtime_server=MagicMock())
        target = captured_subscriptions["target"]
        args = captured_subscriptions["args"]

        with pytest.raises(_StopLoop):
            target(*args)

        built = {(s["routing_key"], s["name"]) for s in recorded}
        expected = {(s.routing_key, queue_name_for(s.callback_name)) for s in SUBSCRIPTIONS}
        assert built == expected

    def test_every_handler_closure_is_registered_in_the_subscription_table(self) -> None:
        """A handler closure with no SUBSCRIPTIONS entry is silently dead.

        Its routing key is still published (see observations/signals.py for
        das.subject.new / das.subject.delete), so nothing consumes those messages
        and its rt_api.* queue is neither gauged nor trimmed by
        check_redis_queues — the durable binding keeps LPUSHing into a list no
        one reads.

        test_built_subscriptions_match_canonical_table cannot catch this: both
        sides of that assertion derive from SUBSCRIPTIONS, so a handler missing
        from the table is missing from both.
        """
        assert _handler_closure_names() == {s.callback_name for s in SUBSCRIPTIONS}

    def test_all_queue_names_are_deduplicated(self) -> None:
        names = all_queue_names()
        assert len(names) == len(set(names))
        # das.tenant.new and das.tenant.update share das_tenant_updated_handler.
        assert names.count(queue_name_for("das_tenant_updated_handler")) == 1
