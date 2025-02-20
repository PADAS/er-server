import logging

from .exceptions import TenantNotFoundException, TenantNotFoundInLocalThreadException
from .thread import get_tenant_settings


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
