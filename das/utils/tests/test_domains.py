"""Tests for utils.tenant.domains."""

from unittest.mock import MagicMock

from django.core.exceptions import DisallowedHost
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


def test_add_new_tenant_domains_includes_hostname_parameter(monkeypatch):
    """When a hostname is passed, it should be added to all settings lists
    even if not present in the cluster domains or alt hosts cache."""
    from django.conf import settings as django_settings

    monkeypatch.setattr(
        "utils.tenant.domains.get_current_cluster_domains",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "utils.tenant.domains.get_alt_hosts_for_tenants",
        MagicMock(return_value=[]),
    )

    with override_settings(
        ALLOWED_HOSTS=["localhost"],
        SERVER_NAMES=["localhost"],
        ALT_SERVER_NAMES=[],
        CORS_ALLOWED_ORIGINS=[],
        CORS_ORIGIN_WHITELIST=[],
        CSRF_TRUSTED_ORIGINS=[],
    ):
        add_new_tenant_domains_to_settings(hostname="newsite.pamdas.org")
        assert "newsite.pamdas.org" in django_settings.ALLOWED_HOSTS
        assert "newsite.pamdas.org" in django_settings.SERVER_NAMES
        assert "newsite.pamdas.org" in django_settings.ALT_SERVER_NAMES
        assert "https://newsite.pamdas.org" in django_settings.CSRF_TRUSTED_ORIGINS


class TestSetTenantByRequestDisallowedHost:
    """Tests for set_tenant_by_request when the host is not in ALLOWED_HOSTS."""

    def test_adds_host_to_allowed_hosts_when_validated_by_tms(self, monkeypatch):
        """When the host is not in ALLOWED_HOSTS but is a valid tenant in TMS,
        it should be added to ALLOWED_HOSTS via add_new_tenant_domains_to_settings."""
        from utils.tenant.managers import set_tenant_by_request

        hostname = "newsite.pamdas.org"
        tenant_data = {"id": "abc-123", "domain": hostname}

        # First get_host() raises DisallowedHost, the cache refresh doesn't
        # help, then we validate via get_tenant_data_by_host which succeeds,
        # add_new_tenant_domains_to_settings is called with the hostname, and
        # the final get_host() works.
        call_count = 0

        def mock_get_host():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise DisallowedHost(f"Invalid HTTP_HOST header: '{hostname}'")
            return hostname

        request = MagicMock()
        request.get_host = mock_get_host
        request.META = {"HTTP_HOST": hostname}

        mock_add_domains = MagicMock()
        monkeypatch.setattr(
            "utils.tenant.managers.add_new_tenant_domains_to_settings",
            mock_add_domains,
        )
        monkeypatch.setattr(
            "utils.tenant.managers.get_tenant_data_by_host",
            MagicMock(return_value=tenant_data),
        )
        monkeypatch.setattr(
            "utils.tenant.managers.set_tenant_data",
            MagicMock(),
        )

        set_tenant_by_request(request)

        # First call: no hostname (cache refresh attempt)
        mock_add_domains.assert_any_call()
        # Second call: with validated hostname
        mock_add_domains.assert_any_call(hostname=hostname)

    def test_raises_when_host_not_in_tms(self, monkeypatch):
        """When the host is not in ALLOWED_HOSTS and not a valid tenant,
        DisallowedHost should propagate."""
        from utils.tenant.exceptions import TenantNotFoundException
        from utils.tenant.managers import set_tenant_by_request

        hostname = "unknown.example.com"

        call_count = 0

        def mock_get_host():
            nonlocal call_count
            call_count += 1
            raise DisallowedHost(f"Invalid HTTP_HOST header: '{hostname}'")

        request = MagicMock()
        request.get_host = mock_get_host
        request.META = {"HTTP_HOST": hostname}

        monkeypatch.setattr(
            "utils.tenant.managers.add_new_tenant_domains_to_settings",
            MagicMock(),
        )
        monkeypatch.setattr(
            "utils.tenant.managers.get_tenant_data_by_host",
            MagicMock(side_effect=TenantNotFoundException(domain=hostname)),
        )

        import pytest

        with pytest.raises(DisallowedHost):
            set_tenant_by_request(request)
