from unittest.mock import Mock, patch

import pytest

from utils.auth0.helpers import (
    get_auth0_custom_domain,
    get_auth0_management_api_access_token,
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


class TestGetAuth0ManagementApiAccessToken:
    @pytest.fixture(autouse=True)
    def mock_settings(self):
        """Mock Django settings for Auth0 Management API configuration."""
        with patch("utils.auth0.helpers.settings") as mock_settings:
            mock_settings.AUTH0_CLIENT_ID_FOR_MANAGEMENT_API = "test_client_id"
            mock_settings.AUTH0_CLIENT_SECRET_FOR_MANAGEMENT_API = "test_client_secret"
            yield mock_settings

    @pytest.fixture(autouse=True)
    def mock_domain_helpers(self):
        """Mock Auth0 domain helper functions."""
        with patch("utils.auth0.helpers.get_auth0_custom_domain") as mock_custom, patch(
            "utils.auth0.helpers.get_auth0_tenant_domain_for_management_api_only"
        ) as mock_noncustom:
            mock_custom.return_value = "custom.auth0.com"
            mock_noncustom.return_value = "tenant.auth0.com"
            yield mock_custom, mock_noncustom

    def test_get_management_api_token_success(self):
        """Test successful token retrieval from Auth0 Management API."""

        with patch("utils.auth0.helpers.GetToken") as mock_get_token_class:
            mock_get_token_instance = Mock()
            mock_get_token_instance.client_credentials.return_value = {
                "access_token": "test_access_token_12345",
                "token_type": "Bearer",
                "expires_in": 86400,
            }
            mock_get_token_class.return_value = mock_get_token_instance

            token = get_auth0_management_api_access_token()

            assert token == "test_access_token_12345"

            # Verify GetToken was initialized with correct parameters
            mock_get_token_class.assert_called_once_with(
                "custom.auth0.com", "test_client_id", client_secret="test_client_secret"
            )

            # Verify client_credentials was called with correct audience
            mock_get_token_instance.client_credentials.assert_called_once_with(
                audience="https://tenant.auth0.com/api/v2/"
            )
