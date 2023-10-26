from typing import Iterable, List, NoReturn

from django.conf import settings

from core.models import DASTenant

SCHEMAS = ("http", "https")


def build_http_urls_from_domains(domains: Iterable[str]) -> List[str]:
    return [f"{schema}://{domain}" for domain in domains for schema in SCHEMAS]


def get_das_tenant_domains() -> List[str]:
    return [tenant["domain"] for tenant in DASTenant.objects.values("domain")]


def add_new_tenant_domains_to_settings() -> NoReturn:
    allowed_hosts = set(settings.ALLOWED_HOSTS)
    tenant_domains = set(get_das_tenant_domains())
    new_tenant_domains = list(tenant_domains.difference(allowed_hosts))

    if not new_tenant_domains:
        return

    settings.ALLOWED_HOSTS.extend(new_tenant_domains)

    new_cors_origins = build_http_urls_from_domains(new_tenant_domains)
    settings.CORS_ALLOWED_ORIGINS.extend(new_cors_origins)
    settings.CORS_ORIGIN_WHITELIST.extend(new_cors_origins)
