import logging

from das_server import celery
from core.query_monitor import configure_query_monitor, EXECUTE_ONCE_INTERVAL

logger = logging.getLogger(__name__)

ELAPSED_THRESHOLD_IN_SECS = 180

@celery.app.task()
def query_monitor():
    logger.info('Celery worker to periodically check running queries')

    # we request to have the query monitor code run only one iteration here as celery scheduling will dictate the
    # execution frequency instead
    configure_query_monitor(interval=EXECUTE_ONCE_INTERVAL,
                            elapsed_threshold=ELAPSED_THRESHOLD_IN_SECS,
                            purge_history=False,
                            query_filter=None,
                            invert_query_filter=None)

