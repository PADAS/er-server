import functools
import logging

import redis

from utils.tenant.exceptions import TenantNotFoundInLocalThreadException
from utils.tenant.thread import get_tenant_settings

logger = logging.getLogger(__name__)


def make_cache_key(key, key_prefix, version):
    tenant = get_tenant_settings()
    key_tokens = (tenant.id, key_prefix, version, key)

    return ":".join(map(str, key_tokens))


def use_multitenant_cache_key(method):
    @functools.wraps(method)
    def tenant_id_prefix_wrapper(self, key, *args, **kwargs):
        try:
            tenant_aware_key = make_cache_key(key, None, None)
            return method(self, tenant_aware_key, *args, **kwargs)
        except TenantNotFoundInLocalThreadException:
            logger.exception("Could not add tenant ID as cache key prefix")
            raise

    return tenant_id_prefix_wrapper


def append_tenant_id_to_cache_key(function):
    @functools.wraps(function)
    def tenant_id_prefix_wrapper(*args, **kwargs):
        if len(args) == 0:
            return function(*args, **kwargs)

        key, other_args = args[0], args[1:]

        try:
            tenant_aware_key = make_cache_key(key, None, None)
            return function(tenant_aware_key, *other_args, **kwargs)
        except TenantNotFoundInLocalThreadException:
            logger.exception("Could not add tenant ID as cache key prefix")
            raise

    return tenant_id_prefix_wrapper


class MultitenantRedisClient:
    def __init__(self, client_url):
        self._redis = redis.from_url(client_url)

    def __getattr__(self, name):
        attribute = getattr(self._redis, name)

        if name.startswith("_") or not callable(attribute):
            return attribute

        return append_tenant_id_to_cache_key(attribute)
