from __future__ import annotations

from unittest.mock import patch

import pytest

from utils.auth0.helpers import (
    create_auth0_management_client,
    get_auth0_custom_domain,
    get_auth0_tenant_domain_for_management_api_only,
)


class TestAuth0Helpers:
    @pytest.fixture
    def mock_settings(self):
        """Mock Django settings with relevant Auth0 configuration."""
        with patch("utils.auth0.helpers.settings") as mock_settings:
            mock_settings.AUTH0_CUSTOM_DOMAIN = "custom.example.com"
            mock_settings.AUTH0_TENANT_DOMAIN = "tenant.auth0.com"
            yield mock_settings

    @pytest.mark.parametrize(
        "func,setting_key",
        [
            (get_auth0_custom_domain, "AUTH0_CUSTOM_DOMAIN"),
            (get_auth0_tenant_domain_for_management_api_only, "AUTH0_TENANT_DOMAIN"),
        ],
    )
    @pytest.mark.parametrize("domain_value", ["", "  "])
    def test_empty_or_whitespace_domain_raises_error(self, func, setting_key, domain_value, mock_settings):
        """Test that empty or whitespace domain values raise ValueError."""
        setattr(mock_settings, setting_key, domain_value)

        with pytest.raises(ValueError, match=f"{setting_key} must be configured and non-empty in settings"):
            func()

    @pytest.mark.parametrize(
        "func,setting_key",
        [
            (get_auth0_custom_domain, "AUTH0_CUSTOM_DOMAIN"),
            (get_auth0_tenant_domain_for_management_api_only, "AUTH0_TENANT_DOMAIN"),
        ],
    )
    @pytest.mark.parametrize(
        "domain,expected_hostname",
        [
            ("test.auth0.com", "test.auth0.com"),
            ("https://test.auth0.com", "test.auth0.com"),
            ("http://test.auth0.com", "test.auth0.com"),
            ("https://test.auth0.com/some/path", "test.auth0.com"),
            ("test.auth0.com/", "test.auth0.com"),
            ("https://test.auth0.com:8080/path?query=value#fragment", "test.auth0.com"),
            ("my-tenant.us.auth0.com", "my-tenant.us.auth0.com"),
            ("enterprise.eu.auth0.com", "enterprise.eu.auth0.com"),
            ("custom.example.com", "custom.example.com"),
        ],
    )
    def test_domain_parsing_returns_hostname(self, func, setting_key, domain, expected_hostname, mock_settings, caplog):
        """Test that various domain formats are parsed to return only the hostname."""
        setattr(mock_settings, setting_key, domain)

        result = func()

        assert result == expected_hostname

        if domain != expected_hostname:
            assert (
                f"'{domain}' was changed to '{expected_hostname}'. Fix {setting_key} to be only the domain."
                in caplog.text
            )
        else:
            assert "was changed to" not in caplog.text


class TestCreateAuth0ManagementClient:
    @pytest.fixture(autouse=True)
    def _clear_factory_cache(self):
        """Clear the @cache between tests so they don't leak state."""
        create_auth0_management_client.cache_clear()
        yield
        create_auth0_management_client.cache_clear()

    @pytest.fixture(autouse=True)
    def mock_settings(self):
        """Mock Django settings for Auth0 Management API configuration."""
        with patch("utils.auth0.helpers.settings") as mock_settings:
            mock_settings.AUTH0_TENANT_DOMAIN = "tenant.auth0.com"
            mock_settings.AUTH0_CLIENT_ID_FOR_MANAGEMENT_API = "test_client_id"
            mock_settings.AUTH0_CLIENT_SECRET_FOR_MANAGEMENT_API = "test_client_secret"
            yield mock_settings

    def test_creates_management_client_with_correct_params(self):
        """Test that the factory constructs ManagementClient with correct kwargs."""
        with patch("utils.auth0.helpers.ManagementClient", autospec=True) as mock_cls:
            create_auth0_management_client()

            mock_cls.assert_called_once_with(
                domain="tenant.auth0.com",
                client_id="test_client_id",
                client_secret="test_client_secret",
            )

    def test_cache_returns_same_instance(self):
        """Test that repeated calls return the same cached instance."""
        with patch("utils.auth0.helpers.ManagementClient", autospec=True) as mock_cls:
            first = create_auth0_management_client()
            second = create_auth0_management_client()

            assert first is second
            mock_cls.assert_called_once()
