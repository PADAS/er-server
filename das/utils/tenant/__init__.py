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
