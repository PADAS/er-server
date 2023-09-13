import logging

from utils.tenant import set_tenant_settings
from utils.tenant.providers import TenantData
from utils.tenant.thread import clear_tenant_settings

logger = logging.getLogger(__name__)


class TenantContextManager:
    def __init__(self, domain: str, *args, **kwargs):
        self.domain = domain
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        if not self.domain:
            raise ValueError("domain cannot be None or empty an string")

        instance = TenantData(domain=self.domain)
        tenant_data = instance.get_tenant_data()
        set_tenant_settings(value=tenant_data)

    def __exit__(self, exc_type, exc_val, exc_tb):
        clear_tenant_settings()
