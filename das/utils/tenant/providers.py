import json
import logging

from core import persistent_storage, tms_api_client
from utils.tenant.exceptions import TenantNotFoundException

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
        logger.info("Getting tenant from Cache for domain %s", self.domain)
        cached_data = persistent_storage.client.get_key(key=self.domain)
        if not cached_data:
            logger.info("Tenant not found at cache")
            return None
        try:
            return json.loads(cached_data)
        except json.JSONDecodeError:
            logger.info("Can't parse tenant from cache for domain %s", self.domain)
            return None

    def _fetch_from_tms(self):
        tenant_data = tms_api_client.client.get_tenant_data(domain=self.domain)
        if not tenant_data:
            raise TenantNotFoundException
        data = json.dumps(tenant_data)
        logger.info("Getting tenant from TMS for domain %s", self.domain)
        self._set_to_cache(data=data)
        return tenant_data

    def _set_to_cache(self, data) -> None:
        logger.info("Setting tenant in cache for domain %s", self.domain)
        persistent_storage.client.insert_key(
            key=TENANT_CACHE_KEY,
            value=data,
            expiration=EXPIRATION_TIME_IN_SECONDS,
        )
