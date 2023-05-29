import logging

from django.db import connections

from .decorator import use_shared_resource
from .interfaces import SharedResourceHandler

logger = logging.getLogger(__name__)


class DatabaseConnectionCloser(SharedResourceHandler):
    def __init__(self, connection):
        self.connection = connection

    def aquire_resource(self):
        logger.debug("aquire shared connection: %s", self.connection)
        self.connection.inc_thread_sharing()

    def release_resource(self):
        self.connection.dec_thread_sharing()
        logger.debug("release shared connection: %s", self.connection)

    def report_error(self, failure):
        logger.warning("Could not close %s connection: %s", self.connection, failure)

    @use_shared_resource
    def close_connection(self):
        self.connection.close_if_unusable_or_obsolete()


def close_old_shared_connections():
    """
    Replace the call of `close_old_connections` since not all the connections belong to the current thread
    """
    logger.debug("Closing old shared connections")
    for connection in connections.all():
        connection_closer = DatabaseConnectionCloser(connection)
        connection_closer.close_connection()
    logger.debug("Shared connections are closed")
