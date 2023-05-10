import logging

from django.db import connections
from django.db.utils import DatabaseError

logger = logging.getLogger("rt_api")


def close_old_shared_connections():
    """
    Replace the call of `close_old_connections` since not all the connections belong to the current thread
    """
    for connection in connections.all():
        try:
            connection.inc_thread_sharing()
            logger.debug("Clossing connection: %s", connection)
            connection.close_if_unusable_or_obsolete()
            logger.debug("Connection closed: %s", connection)
        except DatabaseError as exc:
            logger.warning("Could not close connection: %s", connection)
            logger.exception(exc)

        finally:
            connection.dec_thread_sharing()
