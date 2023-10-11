from unittest import mock

import pytest
from mockredis import MockRedis
from socketio import server

from django.test import TestCase

from rt_api import client
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
        sios = server.Server(client_manager=manager_mock)
        handler = mock.MagicMock()
        sios.on("connect", handler)
        sios._handle_eio_connect("e8ef807c2bbe4418b32de45786d82a52", "sid")
        assert sios.handlers["/"]["connect"] is handler
        assert sios.environ == {"e8ef807c2bbe4418b32de45786d82a52": "sid"}
        self.add_client()
        client.redis_client.hset(client.EXPIRED_CLIENT_TRACES_LIST, "e8ef807c2bbe4418b32de45786d82a52", "message")

        cleanup_disconnected_clients(sios)

        assert sios.environ == {}
        manager_mock.disconnect.assert_called_once_with(
            "e8ef807c2bbe4418b32de45786d82a52", namespace="/", ignore_queue=True
        )
