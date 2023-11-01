from typing import List

from django.conf import settings

from .domains import build_http_urls_from_domains
from .providers import get_current_cluster_domains


def get_das_tenant_urls() -> List[str]:
    tenant_domains = get_current_cluster_domains()
    return build_http_urls_from_domains(tenant_domains)


def get_tenant_aware_cors_allowed_origins() -> List[str]:
    """Generates a dynamic list of CORS allowed origins out of the
    COSRS_ORIGIN_WHITELIST and the current tenant domain
    """
    origins_from_withelist = set(getattr(settings, "CORS_ORIGIN_WHITELIST", []))
    origins_from_das_tenants = set(get_das_tenant_urls())

    return list(origins_from_withelist.union(origins_from_das_tenants))
