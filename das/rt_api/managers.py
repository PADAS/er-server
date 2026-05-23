from __future__ import annotations

import sys
import uuid

import eventlet
import kombu
from redis.exceptions import ConnectionError
from socketio.kombu_manager import KombuManager

from rt_api.client import (
    LIVE_SOCKETIO_QUEUE_HEARTBEAT_INTERVAL,
    LIVE_SOCKETIO_QUEUE_HEARTBEAT_PREFIX,
    LIVE_SOCKETIO_QUEUE_HEARTBEAT_TTL,
    redis_client,
)


class DASKombuManager(KombuManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._queue_name: str | None = None

    def _queue(self):
        # Pin the queue name on first call so the heartbeat key we publish
        # matches the queue actually written to Redis on every reconnect
        # of _listen() inside the same process.
        if self._queue_name is None:
            self._queue_name = f"python-socketio.{uuid.uuid4()}"
            self._touch_live_queue_heartbeat()
            eventlet.spawn(self._live_queue_heartbeat_loop)

        options = {"durable": False, "queue_arguments": {"x-expires": 300000}}
        options.update(self.queue_options)
        return kombu.Queue(self._queue_name, self._exchange(), **options)

    def _live_queue_heartbeat_key(self) -> str:
        return f"{LIVE_SOCKETIO_QUEUE_HEARTBEAT_PREFIX}{self._queue_name}"

    def _touch_live_queue_heartbeat(self) -> None:
        try:
            redis_client.set(
                self._live_queue_heartbeat_key(),
                "1",
                ex=LIVE_SOCKETIO_QUEUE_HEARTBEAT_TTL,
            )
        except Exception:
            self._get_logger().exception("Failed to refresh socketio queue heartbeat key")

    def _live_queue_heartbeat_loop(self) -> None:
        # Refresh forever. Swallow per-iteration errors so a transient Redis
        # blip does not silently kill the heartbeat and let the sweep nuke a
        # live consumer's queue.
        while True:
            eventlet.sleep(LIVE_SOCKETIO_QUEUE_HEARTBEAT_INTERVAL)
            self._touch_live_queue_heartbeat()

    def _thread(self):
        try:
            self._get_logger().info("Starting Kombu manager thread...")
            result = super()._thread()
            self._get_logger().info("Ending Kombu manager thread...")
            return result

        except ConnectionError:
            self._get_logger().exception("RT API server has to die, so EarthRanger will prevail...")
            sys.exit(1)
        except Exception:
            self._get_logger().exception("Ending Kombu manager thread unexpectedly...")
            raise
