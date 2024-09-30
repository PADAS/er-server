"""
Celery tasks for the DB in general, not related to a particular Model.
"""

import logging

from das_server import celery
from utils.tenant.celery import OverAllTenantTask

from .postgresql import (
    execute_sql_query,
    is_posgresql_extension_installed,
    partman_partition_maintenance_query,
)

logger = logging.getLogger(__name__)


@celery.app.task(base=OverAllTenantTask)
def run_partition_maintenance(table_name: str):
    """
    Run the partition maintenance on `table_name`.
    It uses pg_partman behind the scene so make sure to make this postgresql
    extension available before running it. It logs a warning if the extension
    is not available.
    """
    logger.info(f"Running partition maintenance for {table_name}")
    is_pg_partman_extension_available = is_posgresql_extension_installed(extension_name="pg_partman", logger=logger)
    if not is_pg_partman_extension_available:
        logger.warning("pg_partman is not installed, cannot run the maintenance")
    else:
        maintenance_query = partman_partition_maintenance_query(table_name=table_name)
        logger.info(f"maintenance_query to run: {maintenance_query}")
        execute_sql_query(maintenance_query, logger=logger, fetch=True)
        logger.info(f"partman partition maintenance done on table '{table_name}'")
