from kombu.exceptions import InconsistencyError
from kombu.transport import TRANSPORT_ALIASES
from kombu.transport.redis import Channel, Transport


class DasChannel(Channel):
    """Modified Redis Channel.

    When a redis table does not exist, returns an empty list rather than
    raising InconsistencyError.
    """

    def get_table(self, exchange):
        try:
            return super().get_table(exchange)
        except InconsistencyError:
            return []


class DasTransport(Transport):
    Channel = DasChannel


TRANSPORT_ALIASES["redis"] = "das_server.redis:DasTransport"
