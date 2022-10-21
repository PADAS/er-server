from unittest import mock
from socketio import server
from mockredis import MockRedis

from django.test import TestCase
from rt_api.views import cleanup_disconnected_clients
from rt_api import client


class TestRTServer(TestCase):

    @staticmethod
    def _get_mock_socket():
        mock_socket = mock.MagicMock()
        mock_socket.closed = False
        mock_socket.closing = False
        mock_socket.upgraded = False
        mock_socket.session = {}
        return mock_socket

    @staticmethod
    def add_client():
        testdata = client.ClientData(username='x-user',
                                     sid='e8ef807c2bbe4418b32de45786d82a52',
                                     bbox=None)
        client.add_client(testdata.sid, testdata)

    @mock.patch("redis.Redis", MockRedis)
    def test_cleanup_disconnected_clients(self):
        mgr = mock.MagicMock()
        sios = server.Server(client_manager=mgr)
        handler = mock.MagicMock()
        mock_socket = self._get_mock_socket()
        sios.eio.sockets['sid'] = mock_socket
        sios.on('connect', handler)
        sios._handle_eio_connect('sid', 'e8ef807c2bbe4418b32de45786d82a52')
        #sios._handle_connect('sid', '/', None)
        handler.assert_called_once_with('sid', 'e8ef807c2bbe4418b32de45786d82a52')
        self.add_client()
        client.redis_client.hset(client.EXPIRED_CLIENT_TRACES_LIST, 'e8ef807c2bbe4418b32de45786d82a52',
                                 'message')
        num_sockets = len(sios.eio.sockets)
        len_environ = len(sios.environ)
        self.assertEqual(num_sockets, 1)
        self.assertEqual(len_environ, 1)

        cleanup_disconnected_clients(sios)
        _sockets = len(sios.eio.sockets)
        _environ = len(sios.environ)
        self.assertEqual(_sockets, 0)
        self.assertEqual(_environ, 0)
