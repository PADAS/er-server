from unittest.mock import Mock, patch

import pytest
from auth0.exceptions import Auth0Error

from utils.auth0.client import AuthZeroUserProvisioner, AuthZeroUserProvisioningResult


class TestAuthZeroUserProvisioner:
    @pytest.fixture
    def mock_auth0(self):
        """Mock Auth0 client instance with happy path defaults."""
        mock = Mock()

        mock.organizations = Mock()

        mock.tickets = Mock()
        mock.tickets.create_pswd_change.return_value = {"ticket": "some-url"}

        mock.users = Mock()
        mock.users.list.return_value = [{"user_id": "auth0|123456789"}]

        return mock

    @pytest.fixture(autouse=True)
    def mock_settings(self):
        """Mock Django settings for Auth0 configuration."""
        with patch("utils.auth0.client.settings") as mock_settings:
            mock_settings.AUTH0_USER_DB_CONNECTION_NAME = "test-connection"
            yield

    @pytest.fixture(autouse=True)
    def mock_domain_helpers(self):
        """Mock Auth0 domain helper functions."""
        with patch("utils.auth0.client.get_auth0_custom_domain") as mock_custom:
            mock_custom.return_value = "auth.example.com"
            yield

    @pytest.fixture(autouse=True)
    def mock_generated_placeholder_password(self):
        """Mock generate_token to return deterministic password."""
        with patch("utils.auth0.client.generate_token") as mock_password_generator:
            mock_password_generator.return_value = "test-generated-password-123"
            yield

    @pytest.fixture(autouse=True)
    def mock_sleep(self):
        """Mock time.sleep to speed up tests that use retry decorators."""
        with patch("time.sleep") as mock_sleep:
            yield mock_sleep

    @pytest.fixture
    def provisioner_test_instance(self, mock_auth0):
        """Test instance of AuthZeroUserProvisioner with mocked dependencies."""
        return AuthZeroUserProvisioner(
            "testuser",
            "some-org-id",
            token_factory=lambda: "some-access-token",
            auth0_factory=lambda domain, token: mock_auth0,
        )

    def test_init_calls_auth0_factory_with_correct_values(self, mock_auth0):
        """Test that __init__ calls auth0_factory with correct domain and token values."""
        mock_auth0_factory = Mock(return_value=mock_auth0)
        mock_token_factory = Mock(return_value="test-access-token-456")

        provisioner = AuthZeroUserProvisioner(
            "testuser", "some-org-id", token_factory=mock_token_factory, auth0_factory=mock_auth0_factory
        )

        mock_auth0_factory.assert_called_once_with("auth.example.com", "test-access-token-456")

        assert provisioner.auth0 == mock_auth0
        assert provisioner.auth0_organization_id == "some-org-id"
        assert provisioner.connection_name == "test-connection"
        assert provisioner.das_username == "testuser"

    def test_provision_user_success(self, provisioner_test_instance, mock_auth0):
        """Test provision_user method creates user with correct parameters."""
        result = provisioner_test_instance.provision_user()

        mock_auth0.users.create.assert_called_once_with(
            {
                "connection": "test-connection",
                "password": "test-generated-password-123",
                "username": "testuser",
            }
        )

        mock_auth0.users.list.assert_called_once_with(
            q=f'username:"testuser" AND identities.connection:"test-connection"',
            include_totals=False,
            fields=["user_id"],
        )

        mock_auth0.organizations.create_organization_members.assert_called_once_with(
            "some-org-id", {"members": ["auth0|123456789"]}
        )

        mock_auth0.tickets.create_pswd_change.assert_called_once_with(
            {
                "user_id": "auth0|123456789",
            }
        )

        assert result == AuthZeroUserProvisioningResult(auth0_id="auth0|123456789", password_reset_link="some-url")

    def test_provision_user_user_already_exists(self, provisioner_test_instance, mock_auth0, caplog):
        """Test provision_user method logs warning when user already exists (409 error)."""
        mock_auth0.users.create.side_effect = Auth0Error(status_code=409, error_code="", message="")

        result = provisioner_test_instance.provision_user()

        assert "User 'testuser' already exists in Auth0" in caplog.text
        assert result == AuthZeroUserProvisioningResult(auth0_id="auth0|123456789", password_reset_link=None)

        mock_auth0.tickets.create_pswd_change.assert_not_called()

    def test_provision_user_other_create_error(self, provisioner_test_instance, mock_auth0):
        """Test provision_user method raises exception for non-409 Auth0 errors when creating."""
        mock_auth0.users.create.side_effect = Auth0Error(status_code=400, error_code="", message="")

        with pytest.raises(Auth0Error):
            provisioner_test_instance.provision_user()

    def test_provision_user_id_retries_get_succeeds_on_second_attempt(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username succeeds on retry after initial failure."""
        mock_auth0.users.list.side_effect = [[], [{"user_id": "auth0|123456789"}]]

        result = provisioner_test_instance.provision_user()

        assert result == AuthZeroUserProvisioningResult(auth0_id="auth0|123456789", password_reset_link="some-url")

    def test_get_user_id_retries_get_exhausted_after_max_attempts(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username raises ValueError after exhausting retries."""
        mock_auth0.users.list.return_value = []

        with pytest.raises(ValueError, match="User 'testuser' not found in Auth0 connection 'test-connection'"):
            provisioner_test_instance._get_auth0_user_id_by_username()

    def test_get_user_id_retry_with_multiple_users_error(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username retries on multiple users ValueError."""
        mock_auth0.users.list.return_value = [{"user_id": "auth0|123456789"}, {"user_id": "auth0|987654321"}]

        with pytest.raises(
            ValueError, match="Multiple users found with username 'testuser' in Auth0 connection 'test-connection'"
        ):
            provisioner_test_instance._get_auth0_user_id_by_username()
