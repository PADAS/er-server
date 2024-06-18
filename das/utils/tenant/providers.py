import json
import logging
import time
from typing import Callable

from redis.exceptions import ConnectionError

from django.conf import settings

from core import get_alt_domain_cache_client, memory_store_client, tms_api_client
from utils.features import features
from utils.tenant.builder import DjangoSettingsTenantBuilder
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.thread import set_tenant_settings

logger = logging.getLogger(__name__)

TENANT_CACHE_KEY = "tenant"
EXPIRATION_TIME_IN_SECONDS = 604800

alt_domain_cache_client = get_alt_domain_cache_client()


class TenantData:
    domain: str
    get_tenant_data: Callable = None

    def __init__(self, domain: str) -> None:
        self.domain = domain.split(":")[0]

    def get_tenant_data(self):
        if features.tms.is_on():
            return self._get_from_cache_or_tms()
        else:
            return self._get_from_django()

    def _get_from_cache_or_tms(self):
        tenant_data = self._get_from_cache()
        if not tenant_data:
            tenant_data = self._fetch_from_tms()
        if not tenant_data:
            self.domain_from_alts = self._get_from_alt_server_names_hashset()
            self._get_from_cache_or_tms()
        return tenant_data

    def _get_from_alt_server_names_hashset(self):
        logger.debug(
            "Tenant domain not found in cache, nor in the TMS. Checking alt server names for domain %s", self.domain
        )
        primary_domain = alt_domain_cache_client.hget("alt_server_lookup", self.domain)

        if not primary_domain:
            logger.debug(
                "Tenant record not found. Please ensure you have created the tenant and refreshed the cache",
                self.domain,
            )
            return None

        return primary_domain

    def _get_from_cache(self):
        domain_to_use = self.domain_from_alts if hasattr(self, "domain_from_alts") else self.domain
        logger.debug("Getting tenant from cache for domain %s", domain_to_use)

        start_time = time.time()
        try:
            cached_data = memory_store_client.get_key(key=domain_to_use)
        except ConnectionError:
            logger.warning("Could not fetch tenant data from cache due to connection error")
            return None

        if not cached_data:
            logger.debug("Tenant %s not found in cache", domain_to_use)
            return None
        try:
            logger.debug("Retrieved tenant data in %.4f." % (time.time() - start_time))
            return json.loads(cached_data)
        except json.JSONDecodeError:
            logger.warning("Can't parse tenant from cache for domain %s", domain_to_use)
            return None

    def _fetch_from_tms(self):
        domain_to_use = self.domain_from_alts if hasattr(self, "domain_from_alts") else self.domain
        logger.debug("Getting tenant from TMS for domain %s", domain_to_use)

        tenant_data = tms_api_client.get_tenant_data(domain=domain_to_use)
        if not tenant_data:
            logger.debug("Tenant not found in TMS for domain %s", domain_to_use)
            raise TenantNotFoundException(domain=domain_to_use)
        return tenant_data

    def _get_from_django(self):
        tenant = DjangoSettingsTenantBuilder().build()
        return tenant.to_dict()


def get_current_cluster_domains():
    current_cluster_name = settings.CLUSTER_NAME
    current_cluster_namespace = settings.CLUSTER_NAMESPACE

    key = f"{current_cluster_name}-{current_cluster_namespace}"

    try:
        domains = {domain.decode("utf-8") for domain in memory_store_client.get_set_by_key(key=key)}
    except ConnectionError:
        logger.warning("Could not fetch tenant list %s from from cache due to connection error", key)
        domains = set()

    domains.add(settings.SERVER_FQDN)
    return list(domains)


def post_tenant_to_thread(domain):
    instance = TenantData(domain=domain)
    tenant_data = instance.get_tenant_data()
    set_tenant_settings(value=tenant_data)
