from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from das_server import pubsub


class _StopRetrying(Exception):
    """Not a ConnectionError, so it escapes the retry decorator and ends the loop."""


class TestSubscribeRetryWrapping:
    """``subscribe`` keeps its retry-forever behaviour; ``subscribe_without_retry`` does not.

    rt_api's supervision loop calls the undecorated variant so it — and not the
    decorator — owns restart, backoff and the rt_pubsub_listener_restart metric
    for every failure mode, including redis ConnectionError.
    """

    def test_subscribe_wraps_subscribe_without_retry(self) -> None:
        assert pubsub.subscribe.__wrapped__ is pubsub.subscribe_without_retry

    def test_subscribe_retries_redis_connection_error_internally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        attempts = {"n": 0}

        def fake_connection(*args: Any, **kwargs: Any) -> None:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RedisConnectionError("broker down")
            raise _StopRetrying

        sleeps: list[float] = []
        monkeypatch.setattr(pubsub, "Connection", fake_connection)
        monkeypatch.setattr("utils.decorator.time.sleep", lambda d: sleeps.append(d))

        with pytest.raises(_StopRetrying):
            pubsub.subscribe([])

        assert attempts["n"] == 3
        assert sleeps == [1, 1]

    def test_subscribe_without_retry_propagates_redis_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        attempts = {"n": 0}

        def fake_connection(*args: Any, **kwargs: Any) -> None:
            attempts["n"] += 1
            raise RedisConnectionError("broker down")

        def fail_on_sleep(delay: float) -> None:
            raise AssertionError("subscribe_without_retry must not sleep/retry")

        monkeypatch.setattr(pubsub, "Connection", fake_connection)
        monkeypatch.setattr("utils.decorator.time.sleep", fail_on_sleep)

        with pytest.raises(RedisConnectionError):
            pubsub.subscribe_without_retry([])

        assert attempts["n"] == 1
