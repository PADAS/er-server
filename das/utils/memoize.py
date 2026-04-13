from collections import defaultdict
from functools import wraps

from utils.tenant.thread import get_tenant_settings

# Registry of all memoize caches for introspection (memory profiling)
_all_caches = {}


def memoize(function):
    """
    Memoize for single-argument function F(hashable)
    """

    class FunctionCache(dict):
        def __missing__(self, key):
            ret = self[key] = function(key)
            return ret

    caches_per_tenant = defaultdict(FunctionCache)

    cache_name = f"{function.__module__}.{function.__qualname__}"
    _all_caches[cache_name] = caches_per_tenant

    @wraps(function)
    def wrapper(key):
        tenant_domain = get_tenant_settings().domain
        tenant_cache = caches_per_tenant[tenant_domain]

        return tenant_cache[key]

    return wrapper
