"""
A placeholder for publishing message.
"""
import logging
from das_server import celery

send_task = celery.app.send_task

logger = logging.getLogger(__name__)


def publish(message, **kwargs):
    """Broadcast a message.

    :param message: text message
    :parma **kwargs: key value pair parameters
    """

    # noinspection PyBroadException
    try:
        logger.debug(message)

        if message in ('tracking.update'):
            logger.debug('Handling publish for %s with kwargs %s', message, kwargs)
            #send_task('analyzer.tasks.tracking_update', (kwargs['source_id'],))
        else:
            logger.warning('Unknown message: %s', message)

    except Exception:
        logger.exception("Unhandled exception during publish")


