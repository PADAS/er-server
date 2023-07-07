import logging
import threading

from utils.tenant.dataclass import Tenant
from utils.tenant.exceptions import TenantDataclassException

logger = logging.getLogger(__name__)
TENANT_DEFAULT_KEY = "tenant"


def _get_main_thread():
    return threading.main_thread()


def set_tenant_settings(value: dict) -> None:
    local_thread = _get_main_thread()
    try:
        tenant_settings = Tenant.from_dict(value)
    except KeyError as error:
        raise TenantDataclassException(f"Missing key in tenant data: {error}")
    setattr(local_thread, TENANT_DEFAULT_KEY, tenant_settings)
    logger.info(f"Setting tenant settings for host: {tenant_settings.domain}")


def get_tenant_settings() -> Tenant:
    local_thread = _get_main_thread()
    tenant_settings = getattr(local_thread, TENANT_DEFAULT_KEY)
    logger.info(f"Getting tenant settings for host: {tenant_settings.domain}")

    return tenant_settings


def clear_tenant_settings():
    local_thread = _get_main_thread()
    delattr(local_thread, TENANT_DEFAULT_KEY)
