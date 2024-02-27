import logging
from threading import local

from utils.tenant.dataclass import Tenant
from utils.tenant.exceptions import (
    TenantDataclassException,
    TenantNotFoundInLocalThreadException,
)

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
    logger.debug("Setting tenant settings for host: %s", tenant_settings.domain)


def get_tenant_settings() -> Tenant:
    local_thread = _get_local_thread()
    try:
        tenant_settings = getattr(local_thread, TENANT_DEFAULT_KEY)
        logger.debug("Getting tenant settings for host: %s", tenant_settings.domain)

        return tenant_settings
    except AttributeError:
        raise TenantNotFoundInLocalThreadException()


def has_tenant_settings():
    local_thread = _get_local_thread()
    return hasattr(local_thread, TENANT_DEFAULT_KEY)


def clear_tenant_settings():
    local_thread = _get_local_thread()
    if hasattr(local_thread, TENANT_DEFAULT_KEY):
        tenant_domain = getattr(local_thread, TENANT_DEFAULT_KEY).domain
        delattr(local_thread, TENANT_DEFAULT_KEY)
        logger.debug("Clearing tenant settings from thread for host: %s", tenant_domain)
