from typing import Iterable, List, NoReturn

from django.conf import settings

from core import get_alt_domain_cache_client, tms_api_client
from utils.tenant.providers import get_current_cluster_domains

SCHEMAS = ("http", "https")

alt_domain_cache_client = get_alt_domain_cache_client()


def get_alt_server_names_for_tenant(tenant):
    envSettings = tenant.get("envSettings", {}) or {}

    all_server_names = envSettings.get("allServerNames")
    alt_server_names = envSettings.get("altServerNames")

    all_server_names = all_server_names or []
    alt_server_names = alt_server_names or []

    return list(set(all_server_names + alt_server_names))


def build_http_urls_from_domains(domains: Iterable[str]) -> List[str]:
    return [f"{schema}://{domain}" for domain in domains for schema in SCHEMAS]


def populate_alt_server_lookup_cache(all_tenant_data):
    """Populates the alt_server_lookup cache with data from all tenants, considering both alt_server_names
    and all_server_names."""
    for tenant in all_tenant_data:
        primary_domain = tenant.get("domain")
        server_names = get_alt_server_names_for_tenant(tenant)

        if primary_domain and server_names:
            for server_name in server_names:
                alt_domain_cache_client.hset("alt_server_lookup", server_name, primary_domain)
                # later, to get the primary domain -- alt_domain_cache_client.hget("alt_server_lookup", server_name)


def add_new_tenant_domains_to_settings() -> NoReturn:
    # if we are running in management collect static, then there is no config
    if getattr(settings, "COLLECT_STATIC_NO_DB", False):
        return

    full_tenant_list = tms_api_client.list_tenants()

    tenants_in_current_cluster = [
        tenant
        for tenant in full_tenant_list
        if tenant["clusterName"] == settings.CLUSTER_NAME and tenant["clusterNamespace"] == settings.CLUSTER_NAMESPACE
    ]

    populate_alt_server_lookup_cache(tenants_in_current_cluster)

    alt_hosts_for_tenants = [
        server for tenant in tenants_in_current_cluster for server in get_alt_server_names_for_tenant(tenant)
    ]

    allowed_hosts = set(settings.ALLOWED_HOSTS) | set(alt_hosts_for_tenants)
    tenant_domains = set(get_current_cluster_domains())
    new_tenant_domains = list(tenant_domains.difference(allowed_hosts))

    if not new_tenant_domains:
        return

    settings.ALLOWED_HOSTS.extend(new_tenant_domains)
    settings.SERVER_NAMES.extend(new_tenant_domains)
    settings.ALT_SERVER_NAMES.extend(new_tenant_domains)

    new_cors_origins = build_http_urls_from_domains(new_tenant_domains)
    settings.CORS_ALLOWED_ORIGINS.extend(new_cors_origins)
    settings.CORS_ORIGIN_WHITELIST.extend(new_cors_origins)
