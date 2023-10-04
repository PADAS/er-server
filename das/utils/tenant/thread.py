import logging
from threading import local

from django_multitenant.utils import set_current_tenant

from core.models import DASTenant
from utils.tenant.dataclass import Tenant
from utils.tenant.exceptions import (
    TenantDataclassException,
    TenantNotFoundInLocalThreadException,
)
from utils.tenant.managers import UnsetDASTenantContextManager
from utils.tenant.providers import TenantData

logger = logging.getLogger(__name__)
TENANT_DEFAULT_KEY = "tenant_object"

_local_thread = local()


def _get_local_thread():
    return _local_thread


def set_tenant_settings(value: dict) -> None:
    local_thread = _get_local_thread()
    try:
        tenant_settings = Tenant.from_dict(value)
    except KeyError as error:
        raise TenantDataclassException(f"Missing key in tenant data: {error}")
    setattr(local_thread, TENANT_DEFAULT_KEY, tenant_settings)
    logger.info("Setting tenant settings for host: %s", tenant_settings.domain)


def get_tenant_settings() -> Tenant:
    local_thread = _get_local_thread()
    try:
        tenant_settings = getattr(local_thread, TENANT_DEFAULT_KEY)
        logger.debug("Getting tenant settings for host: %s", tenant_settings.domain)

        return tenant_settings
    except AttributeError:
        raise TenantNotFoundInLocalThreadException()


def clear_tenant_settings():
    local_thread = _get_local_thread()
    if hasattr(local_thread, TENANT_DEFAULT_KEY):
        tenant_domain = getattr(local_thread, TENANT_DEFAULT_KEY).domain
        delattr(local_thread, TENANT_DEFAULT_KEY)
        logger.debug("Clearing tenant settings from thread for host: %s", tenant_domain)


def set_tenant(domain):
    """
    Single function to set both the Tenant and the DASTenant in the current thread
    """
    instance = TenantData(domain=domain)
    tenant_data = instance.get_tenant_data()
    tenant_id = tenant_data.get("id")
    with UnsetDASTenantContextManager():
        das_tenant = DASTenant.objects.get(id=tenant_id)
    set_tenant_settings(value=tenant_data)
    set_current_tenant(tenant=das_tenant)
