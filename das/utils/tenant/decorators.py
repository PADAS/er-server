import functools

from utils.features import features
from utils.tenant import get_tenant_settings


def append_tenant_domain(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if features.tms.is_on():
            kwargs["domain"] = get_tenant_settings().domain
        return func(*args, **kwargs)

    return wrapper
