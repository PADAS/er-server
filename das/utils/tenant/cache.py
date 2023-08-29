from utils.tenant.thread import get_tenant_settings


def make_cache_key(key, key_prefix, version):
    tenant = get_tenant_settings()
    key_tokens = (tenant.id, key_prefix, version, key)

    return ":".join(map(str, key_tokens))
