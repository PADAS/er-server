from unittest import mock

from rt_api.client import (
    LIVE_SOCKETIO_QUEUE_HEARTBEAT_PREFIX,
    LIVE_SOCKETIO_QUEUE_HEARTBEAT_TTL,
)
from rt_api.managers import DASKombuManager


class TestDASKombuManagerLiveQueueHeartbeat:
    def _make_manager(self):
        # KombuManager.__init__ opens a publisher_connection — bypass it so
        # the unit test stays in-process.
        with mock.patch("rt_api.managers.KombuManager.__init__", lambda self, *a, **kw: None):
            mgr = DASKombuManager()
        mgr._queue_name = None
        mgr.queue_options = {}
        mgr.exchange_options = {}
        mgr._exchange = mock.MagicMock(return_value=mock.sentinel.exchange)
        mgr.channel = "socketio"
        mgr.logger = None
        mgr._get_logger = mock.MagicMock()
        return mgr

    def test_first_queue_call_writes_heartbeat_and_spawns_refresh_loop(self, monkeypatch):
        rc = mock.MagicMock()
        spawn = mock.MagicMock()
        monkeypatch.setattr("rt_api.managers.redis_client", rc)
        monkeypatch.setattr("rt_api.managers.eventlet.spawn", spawn)

        mgr = self._make_manager()
        with mock.patch("rt_api.managers.kombu.Queue") as fake_queue:
            mgr._queue()

        assert mgr._queue_name is not None
        assert mgr._queue_name.startswith("python-socketio.")
        rc.set.assert_called_once_with(
            f"{LIVE_SOCKETIO_QUEUE_HEARTBEAT_PREFIX}{mgr._queue_name}",
            "1",
            ex=LIVE_SOCKETIO_QUEUE_HEARTBEAT_TTL,
        )
        spawn.assert_called_once_with(mgr._live_queue_heartbeat_loop)
        fake_queue.assert_called_once()

    def test_queue_name_is_stable_across_reconnects(self, monkeypatch):
        # Kombu's _listen() may call _queue() again on retry. The heartbeat
        # is keyed by name, so we must not mint a new name (and a new
        # heartbeat) on every call — that would leak heartbeat keys.
        rc = mock.MagicMock()
        spawn = mock.MagicMock()
        monkeypatch.setattr("rt_api.managers.redis_client", rc)
        monkeypatch.setattr("rt_api.managers.eventlet.spawn", spawn)

        mgr = self._make_manager()
        with mock.patch("rt_api.managers.kombu.Queue"):
            mgr._queue()
            first_name = mgr._queue_name
            mgr._queue()

        assert mgr._queue_name == first_name
        # Heartbeat written once on first call, refresh loop spawned once.
        assert rc.set.call_count == 1
        assert spawn.call_count == 1

    def test_heartbeat_refresh_swallows_redis_errors(self, monkeypatch):
        rc = mock.MagicMock()
        rc.set.side_effect = RuntimeError("redis blip")
        monkeypatch.setattr("rt_api.managers.redis_client", rc)

        mgr = self._make_manager()
        mgr._queue_name = "python-socketio.test"

        # Should not raise — a transient Redis failure must not kill the
        # refresh loop and let the sweep nuke a live consumer's queue.
        mgr._touch_live_queue_heartbeat()
