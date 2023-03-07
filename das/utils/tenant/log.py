import logging

from .exceptions import TenantNotFoundException, TenantNotFoundInLocalThreadException
from .thread import get_tenant_settings


def add_log_filters():
    tenant_filter = TenantFilter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(tenant_filter)


class TenantFilter(logging.Filter):
    """
    This logging filter injects tenant information into the log record.
    """

    def filter(self, record):
        try:
            tenant = get_tenant_settings()
            record.tenant = tenant.domain
        except (TenantNotFoundException, TenantNotFoundInLocalThreadException):
            pass
        return True
