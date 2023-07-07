import json
import logging
import time

from core import memory_store_client, tms_api_client

logger = logging.getLogger(__name__)

TENANT_CACHE_KEY = "tenant"
EXPIRATION_TIME_IN_SECONDS = 604800


class TenantData:
    domain: str

    def __init__(self, domain: str) -> None:
        self.domain = domain

    def get(self):
        tenant_data = self._get_from_cache()
        if not tenant_data:
            tenant_data = self._fetch_from_tms()
        return tenant_data

    def _get_from_cache(self):
        logger.info("Getting tenant from cache for domain %s", self.domain)
        start_time = time.time()
        cached_data = memory_store_client.get_key(key=self.domain)
        if not cached_data:
            logger.info("Tenant not found at cache")
            return None
        try:
            logger.info("Gotten tenant data in %.4f." % (time.time() - start_time))
            return json.loads(cached_data)
        except json.JSONDecodeError:
            logger.info("Can't parse tenant from cache for domain %s", self.domain)
            return None

    def _fetch_from_tms(self):
        logger.info("Getting tenant from TMS for domain %s", self.domain)
        tenant_data = tms_api_client.get_tenant_data(domain=self.domain)
        if not tenant_data:
            logger.info("Tenant not found at TMS for domain %s", self.domain)
        return tenant_data

    @classmethod
    def get_all_tenant_domains(cls):
        return [domain.decode("utf-8") for domain in memory_store_client.get_all_keys()]
