from collections import defaultdict
from functools import wraps

from utils.tenant.thread import get_tenant_settings


def memoize(function):
    """
    Memoize for single-argument function F(hashable)
    """

    class FunctionCache(dict):
        def __missing__(self, key):
            ret = self[key] = function(key)
            return ret

    caches_per_tenant = defaultdict(FunctionCache)

    @wraps(function)
    def wrapper(key):
        tenant_domain = get_tenant_settings().domain
        tenant_cache = caches_per_tenant[tenant_domain]

        return tenant_cache[key]

    return wrapper
