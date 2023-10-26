from unittest import mock

import pytest
from mockredis import MockRedis
from socketio import server

from django.test import TestCase

from rt_api import client
from rt_api.server import DasSocketIOServer
from rt_api.views import cleanup_disconnected_clients


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRTServer(TestCase):
    def add_client(self):
        testdata = client.ClientData(
            username="x-user",
            sid="e8ef807c2bbe4418b32de45786d82a52",
            bbox=None,
            tenant_id=self.tenant_settings.id,
            domain=self.tenant_settings.domain,
        )
        client.add_client(testdata.sid, testdata)

    @mock.patch("redis.Redis", MockRedis)
    def test_cleanup_disconnected_clients(self):
        manager_mock = mock.MagicMock()
        manager_mock.sid_from_eio_sid.return_value = "e8ef807c2bbe4418b32de45786d82a52"
        socket_mock = mock.MagicMock()
        sios = server.Server(client_manager=manager_mock)
        sios.eio.sockets = {"e8ef807c2bbe4418b32de45786d82a52": socket_mock}
        handler = mock.MagicMock()
        sios.on("connect", handler)
        sios._handle_eio_connect("e8ef807c2bbe4418b32de45786d82a52", "sid")
        assert sios.handlers["/"]["connect"] is handler
        self.add_client()
        client.redis_client.hset(client.EXPIRED_CLIENT_TRACES_LIST, "e8ef807c2bbe4418b32de45786d82a52", "message")

        cleanup_disconnected_clients(sios)

        manager_mock.disconnect.assert_called_once_with(
            "e8ef807c2bbe4418b32de45786d82a52", namespace="/", ignore_queue=True
        )

    def test_cors_allowed_origins_are_modifiable(self):
        cors_allowed = ["http://somewhere-else.pamdas.org"]
        sios = DasSocketIOServer()
        original_cors_allowed = sios.eio.cors_allowed_origins

        sios.set_cors_allowed_origins(cors_allowed)

        assert original_cors_allowed is None
        assert sios.eio.cors_allowed_origins == cors_allowed

    def test_set_cors_allowed_origins_failed_on_str_arg(self):
        sios = DasSocketIOServer()

        with pytest.raises(TypeError):
            sios.set_cors_allowed_origins("http://foo.bar.org;https://foo.bar.org")

    def test_set_cors_allowed_origins_failed_on_non_iterable_arg(self):
        sios = DasSocketIOServer()

        with pytest.raises(TypeError):
            sios.set_cors_allowed_origins(33)

    def test_set_cors_allowed_origins_failed_on_empty_list(self):
        sios = DasSocketIOServer()

        with pytest.raises(ValueError):
            sios.set_cors_allowed_origins([])
