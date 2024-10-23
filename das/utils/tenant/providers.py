import datetime
import json
import logging
import time

from redis.exceptions import ConnectionError

from django.conf import settings

from core import tenant_document_cache_client, tms_api_client
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.thread import set_tenant_settings

logger = logging.getLogger(__name__)

TENANTS_CACHE_KEY = "tenant_domains"
ALT_SERVER_LOOKUP_CACHE_KEY = "alt_server_lookup"
TENANT_CACHE_TTL = 60 * 60 * 24  # 1 day, in seconds


def get_alt_server_names_for_tenant(tenant):
    envSettings = tenant.get("envSettings", {})

    all_server_names = envSettings.get("allServerNames")
    alt_server_names = envSettings.get("altServerNames")

    all_server_names = all_server_names or []
    alt_server_names = alt_server_names or []

    server_names = set()
    for server_name in set(all_server_names + alt_server_names):
        server_names.add(server_name)
        if ":" in server_name:
            server_names.add(server_name.split(":")[0])
    return server_names


def make_tenant_cache_key(domain: str) -> str:
    return f"tenant:{domain}"


def update_tenant_in_cache(
    tenant_data: dict, tenants_cache_key=TENANTS_CACHE_KEY, alt_server_lookup_cache_key=ALT_SERVER_LOOKUP_CACHE_KEY
) -> None:
    """Update the tenant data in the cache.
    tenants_cache_key and alt_server_lookup_cache_key overrides are used for staging a big update in a temporary key
    """
    domain = tenant_data.get("domain")
    tenant_document_cache_client.insert_key(
        make_tenant_cache_key(domain), json.dumps(tenant_data), ttl=TENANT_CACHE_TTL
    )
    tenant_document_cache_client.insert_set(tenants_cache_key, domain)

    server_names = get_alt_server_names_for_tenant(tenant_data)

    if domain and server_names:
        for server_name in server_names:
            tenant_document_cache_client.insert_hash_set(alt_server_lookup_cache_key, server_name, domain)


def update_all_tenants_in_cache(tenants: list) -> None:

    # use temporary keys to stage the update
    now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    temp_tenants_cache_key = f"{TENANTS_CACHE_KEY}_{now}"
    temp_alt_server_lookup_cache_key = f"{ALT_SERVER_LOOKUP_CACHE_KEY}_{now}"

    for tenant in tenants:
        if (
            tenant["clusterName"] == settings.CLUSTER_NAME and tenant["clusterNamespace"] == settings.CLUSTER_NAMESPACE
        ) or tenant["domain"] == settings.SERVER_FQDN:
            update_tenant_in_cache(tenant, temp_tenants_cache_key, temp_alt_server_lookup_cache_key)

    with tenant_document_cache_client.connection.pipeline() as pipe:
        pipe.delete(ALT_SERVER_LOOKUP_CACHE_KEY)
        pipe.rename(temp_alt_server_lookup_cache_key, ALT_SERVER_LOOKUP_CACHE_KEY)
        pipe.expire(ALT_SERVER_LOOKUP_CACHE_KEY, TENANT_CACHE_TTL)
        pipe.delete(TENANTS_CACHE_KEY)
        pipe.rename(temp_tenants_cache_key, TENANTS_CACHE_KEY)
        pipe.expire(TENANTS_CACHE_KEY, TENANT_CACHE_TTL)
        pipe.execute()


def is_tenants_cache_empty() -> bool:
    return tenant_document_cache_client.get_set_size(TENANTS_CACHE_KEY) == 0


def refresh_tenants_cache() -> None:
    logger.info("Refreshing tenant cache")
    tenants = tms_api_client.list_tenants()
    if not tenants:
        logger.error("No tenants found in TMS")
        return
    update_all_tenants_in_cache(tenants)
    logger.info("Refreshing tenant cache complete, found %d tenants", len(tenants))


def get_tenant_domain_from_alt_server_name(host_name: str) -> str:
    logger.info("Getting tenant domain from alt server name %s", host_name)
    domain = tenant_document_cache_client.get_hash_set(ALT_SERVER_LOOKUP_CACHE_KEY, host_name)
    if not domain:
        logger.error("Tenant domain not found for alt server name %s", host_name)
        raise TenantNotFoundException(domain=host_name)
    return domain.decode("utf-8") if isinstance(domain, bytes) else domain


def get_alt_hosts_for_tenants() -> set:
    alt_hosts = set()
    for key in tenant_document_cache_client.get_keys_hash_set(ALT_SERVER_LOOKUP_CACHE_KEY):
        alt_hosts.add(key.decode("utf-8") if isinstance(key, bytes) else key)
    return alt_hosts


def get_tenant_data_by_host(host_name: str) -> dict:
    try:
        instance = TenantData(domain=host_name)
        tenant_data = instance.get_tenant_data()
    except TenantNotFoundException:
        domain = get_tenant_domain_from_alt_server_name(host_name)
        instance = TenantData(domain=domain)
        tenant_data = instance.get_tenant_data()
    return tenant_data


class TenantData:
    domain: str

    def __init__(self, domain: str) -> None:
        self.domain = domain.split(":")[0]

    def get_tenant_data(self):
        return self._get_from_cache_or_tms(self.domain)

    def _get_from_cache_or_tms(self, hostname: str):
        tenant_data = self._get_from_cache(hostname)
        if not tenant_data:
            tenant_data = self._fetch_from_tms(hostname)
            if tenant_data:
                update_tenant_in_cache(tenant_data, TENANTS_CACHE_KEY, ALT_SERVER_LOOKUP_CACHE_KEY)

        if not tenant_data:
            logger.error(
                "Tenant record not found. Please ensure you have created the tenant and refreshed the cache",
            )
            raise TenantNotFoundException(domain=hostname)

        return tenant_data

    def _get_from_cache(self, hostname):
        logger.debug("Getting tenant from cache for domain %s", hostname)

        start_time = time.time()
        try:
            cached_data = tenant_document_cache_client.get_key(make_tenant_cache_key(hostname))
        except ConnectionError:
            logger.warning("Could not fetch tenant data from cache due to connection error")
            return None

        if not cached_data:
            logger.debug("Tenant %s not found in cache", hostname)
            return None
        try:
            logger.debug("Retrieved tenant data in %.4f." % (time.time() - start_time))
            return json.loads(cached_data)
        except json.JSONDecodeError:
            logger.warning("Can't parse tenant from cache for domain %s", hostname)
            return None

    def _fetch_from_tms(self, hostname):
        logger.debug("Getting tenant from TMS for domain %s", hostname)

        tenant_data = tms_api_client.get_tenant_data(domain=hostname)

        if not tenant_data:
            logger.debug("Tenant not found in TMS for domain %s", hostname)
        return tenant_data


def get_current_cluster_domains() -> set:
    if is_tenants_cache_empty():
        refresh_tenants_cache()

    tenants = tenant_document_cache_client.get_set_by_key(TENANTS_CACHE_KEY)
    tenants = set(tenant.decode("utf-8") if isinstance(tenant, bytes) else tenant for tenant in tenants)
    tenants.add(settings.SERVER_FQDN)
    return tenants


def post_tenant_to_thread(domain: str) -> None:
    instance = TenantData(domain=domain)
    tenant_data = instance.get_tenant_data()
    set_tenant_settings(value=tenant_data)
