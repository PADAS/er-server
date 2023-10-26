import json
import logging
import time
from typing import Callable

from django.conf import settings

from core import memory_store_client, tms_api_client
from utils.features import features
from utils.tenant.builder import DjangoSettingsTenantBuilder
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.thread import set_tenant_settings

logger = logging.getLogger(__name__)

TENANT_CACHE_KEY = "tenant"
EXPIRATION_TIME_IN_SECONDS = 604800


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
            raise TenantNotFoundException(domain=self.domain)
        return tenant_data

    def _get_from_django(self):
        tenant = DjangoSettingsTenantBuilder().build()
        return tenant.to_dict()


def get_current_cluster_domains(cls):
    current_cluster_name = settings.CLUSTER_NAME
    current_cluster_namespace = settings.CLUSTER_NAMESPACE

    key = f"{current_cluster_name}-{current_cluster_namespace}"

    return [domain.decode("utf-8") for domain in memory_store_client.get_set_by_key(key=key)]


def post_tenant_to_thread(domain):
    instance = TenantData(domain=domain)
    tenant_data = instance.get_tenant_data()
    set_tenant_settings(value=tenant_data)
