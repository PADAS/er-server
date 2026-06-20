import logging

from django.apps import AppConfig


class DasServerConfig(AppConfig):
    name = "das_server"
    verbose_name = "DAS Server"

    def ready(self):
        # NOTE: metrics initialization (configure_metrics) is intentionally NOT
        # called here. The PeriodicExportingMetricReader spawns a background
        # thread, and gunicorn/celery fork workers after Django app-loading —
        # threads do not survive fork. Metrics are initialized per-worker from
        # gunicorn's post_fork hook and celery's worker_process_init signal.
        add_log_filters()


def add_log_filters():
    """Add any filters now that require the django subsystem to be up and running"""
    from utils.tenant.log import TenantFilter

    tenant_filter = TenantFilter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(tenant_filter)
