from unittest.mock import patch

import pytest

from utils.auth0.helpers import (
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
