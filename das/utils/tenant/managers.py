import logging
from dataclasses import asdict

from django_multitenant.utils import get_current_tenant, set_current_tenant

from core.models import DASTenant
from utils.tenant import get_tenant_settings, set_tenant_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException
from utils.tenant.providers import TenantData
from utils.tenant.thread import clear_tenant_settings

logger = logging.getLogger(__name__)


class TenantContextManager:
    def __init__(self, domain: str, *args, **kwargs):
        self.domain = domain
        self.args = args
        self.kwargs = kwargs
        self.previous_tenant_settings = None
        self.previous_tenant = None

    def __enter__(self):
        if not self.domain:
            raise ValueError("domain cannot be None or empty an string")

        tenant_data = TenantData(domain=self.domain).get_tenant_data()
        tenant = DASTenant.objects.get(id=tenant_data["id"])
        try:
            self.previous_tenant_settings = get_tenant_settings()
        except TenantNotFoundInLocalThreadException:
            pass

        self.previous_tenant = get_current_tenant()

        set_tenant_settings(value=tenant_data)
        set_current_tenant(tenant)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.previous_tenant_settings:
            set_tenant_settings(asdict(self.previous_tenant_settings))
        else:
            clear_tenant_settings()
        set_current_tenant(self.previous_tenant)
