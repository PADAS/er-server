"""Tests for utils.tenant.domains."""

from unittest.mock import MagicMock

from django.test import override_settings

from utils.tenant.domains import add_new_tenant_domains_to_settings


def test_add_new_tenant_domains_no_duplicates_when_allowed_hosts_is_server_names(
    monkeypatch,
):
    """When ALLOWED_HOSTS and SERVER_NAMES are the same list (e.g. local_settings_docker),
    extending both would add each domain twice. Assert each new domain is added only once.
    """
    shared = ["root.dev.pamdas.org", "localhost:9000"]
    new_domain = "standrews.dev.pamdas.org"

    monkeypatch.setattr(
        "utils.tenant.domains.get_current_cluster_domains",
        MagicMock(return_value=[new_domain]),
    )
    monkeypatch.setattr(
        "utils.tenant.domains.get_alt_hosts_for_tenants",
        MagicMock(return_value=[]),
    )

    with override_settings(
        ALLOWED_HOSTS=shared,
        SERVER_NAMES=shared,
        ALT_SERVER_NAMES=[],
        CORS_ALLOWED_ORIGINS=[],
        CORS_ORIGIN_WHITELIST=[],
        CSRF_TRUSTED_ORIGINS=[],
    ):
        add_new_tenant_domains_to_settings()

    count = shared.count(new_domain)
    assert count == 1, f"expected {new_domain} once in ALLOWED_HOSTS, got {count}"
