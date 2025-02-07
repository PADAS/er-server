import logging

from django.apps import AppConfig
from django.conf import settings

import utils.stats


class DasServerConfig(AppConfig):
    name = "das_server"
    verbose_name = "DAS Server"

    def ready(self):
        if settings.DISABLE_STATSD:
            utils.stats.statsd.disable_telemetry()
        add_log_filters()


def add_log_filters():
    """Add any filters now that require the django subsystem to be up and running"""
    from utils.tenant.log import TenantFilter

    tenant_filter = TenantFilter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(tenant_filter)
