from unittest.mock import MagicMock

from kombu.exceptions import InconsistencyError

from das_server.redis import DasChannel


class TestDasChannel:
    def test_channel_returns_empty_list_on_inconsistency_error(self, monkeypatch):
        connection_mock = MagicMock()
        monkeypatch.setattr("kombu.transport.redis.Channel.__init__", MagicMock(return_value=None))
        monkeypatch.setattr("kombu.transport.redis.Channel._create_client", MagicMock)
        monkeypatch.setattr("kombu.transport.redis.Channel.get_table", MagicMock(side_effect=InconsistencyError))
        channel = DasChannel(connection_mock)
        exchange = MagicMock()

        result = channel.get_table(exchange)

        assert result == []
