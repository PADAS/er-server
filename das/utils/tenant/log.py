import logging

from .exceptions import TenantNotFoundException, TenantNotFoundInLocalThreadException


class TenantFilter(logging.Filter):
    """
    This logging filter injects tenant information into the log record.
    """

    get_tenant_settings = None

    def filter(self, record):
        if self.get_tenant_settings is None:
            # delayed import because log filters are set before django apps are initialized
            from .managers import get_tenant_settings

            self.get_tenant_settings = get_tenant_settings

        try:
            tenant = self.get_tenant_settings()
            record.tenant = tenant.domain
        except (TenantNotFoundException, TenantNotFoundInLocalThreadException):
            pass
        return True
