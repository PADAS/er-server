"""
Celery tasks to run on the database. These tasks are not tied to a particular
django application.
"""

import logging

from celery_once import QueueOnce

from das_server import celery

from . import task_helpers as utils_db_task_helpers

logger = logging.getLogger(__name__)


@celery.app.task(
    base=QueueOnce,
    default_retry_delay=60,
    max_retries=5,
    retry_backoff=30,
    retry_backoff_max=10 * 60,
)
def run_partition_maintenance_proc() -> None:
    """
    Run the partition maintenance procedure on all partitionned tables.
    """
    logger.info(f"Running the partition maintenance procedure")
    utils_db_task_helpers.run_partition_maintenance_proc(logger=logger)
