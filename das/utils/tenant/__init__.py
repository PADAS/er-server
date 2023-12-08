import base64
import uuid

from utils.tenant.builder import DjangoSettingsTenantBuilder
from utils.tenant.cache import make_cache_key
from utils.tenant.dataclass import Tenant
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import set_tenant
from utils.tenant.thread import get_tenant_settings, set_tenant_settings

__all__ = (
    "DjangoSettingsTenantBuilder",
    "Tenant",
    "TenantNotFoundException",
    "get_tenant_settings",
    "make_cache_key",
    "set_tenant_settings",
    "set_tenant",
)


def get_ui_site_name(tenant_settings):
    return f"EarthRanger {tenant_settings.domain}"


def get_ui_site_url(tenant_settings):
    return tenant_settings.url


def shorten_tenant_id(tenant_id: uuid.UUID) -> str:
    """Shorten the UUID id to a base64 encoded representation that is 22 characters long

    Args:
        tenant_id (uuid.UUID): the tenant id to shorten

    Returns:
        str: the shortened string
    """
    return str(base64.urlsafe_b64encode(tenant_id.bytes), "utf-8").rstrip("=")


def lengthen_tenant_id(short_id: str) -> uuid.UUID:
    """restores the shortened string representation of the tenant id

    Args:
        id (str): shortened and base64 encoded UUID, see shorten_tenant_id

    Returns:
        uuid.UUID: restored UUID
    """
    return uuid.UUID(bytes=base64.urlsafe_b64decode(f"{short_id}=="))
