from typing import Iterable, List

from django.conf import settings

from utils.tenant.providers import (
    get_alt_hosts_for_tenants,
    get_current_cluster_domains,
)

SCHEMAS = ("http", "https")


def build_http_urls_from_domains(domains: Iterable[str]) -> List[str]:
    return [f"{schema}://{domain}" for domain in domains for schema in SCHEMAS]


def add_new_tenant_domains_to_settings() -> None:
    # if we are running in management collect static, then there is no config
    if getattr(settings, "COLLECT_STATIC_NO_DB", False):
        return

    allowed_hosts = set(settings.ALLOWED_HOSTS)
    tenant_domains = set(get_current_cluster_domains()) | set(get_alt_hosts_for_tenants())
    new_tenant_domains = list(tenant_domains.difference(allowed_hosts))

    if not new_tenant_domains:
        return

    settings.ALLOWED_HOSTS.extend(new_tenant_domains)
    settings.SERVER_NAMES.extend(new_tenant_domains)
    settings.ALT_SERVER_NAMES.extend(new_tenant_domains)

    new_cors_origins = build_http_urls_from_domains(new_tenant_domains)
    settings.CORS_ALLOWED_ORIGINS.extend(new_cors_origins)
    settings.CORS_ORIGIN_WHITELIST.extend(new_cors_origins)
    settings.CSRF_TRUSTED_ORIGINS.extend(new_tenant_domains)
