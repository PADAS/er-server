from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from auth0.management import ManagementClient
from auth0.management.core.api_error import ApiError
from auth0.management.errors import ConflictError

from utils.auth0.client import AuthZeroUserProvisioner, AuthZeroUserProvisioningResult


class TestAuthZeroUserProvisioner:
    @pytest.fixture
    def mock_auth0(self):
        """Mock ManagementClient with happy path defaults."""
        mock = Mock(spec=ManagementClient)

        mock.organizations = Mock()
        mock.organizations.members = Mock()

        mock.tickets = Mock()
        mock.tickets.change_password.return_value = Mock(ticket="some-url")

        mock.users = Mock()
        mock.users.list.return_value = [Mock(user_id="auth0|123456789")]

        return mock

    @pytest.fixture(autouse=True)
    def mock_settings(self):
        """Mock Django settings for Auth0 configuration."""
        with patch("utils.auth0.client.settings") as mock_settings:
            mock_settings.AUTH0_USER_DB_CONNECTION_NAME = "test-connection"
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
            das_user_username="testuser",
            das_user_email="testuser@example.com",
            das_site_name="foo",
            auth0_organization_id="some-org-id",
            client_factory=lambda: mock_auth0,
        )

    def test_init_calls_client_factory(self, mock_auth0):
        """Test that __init__ calls client_factory and stores the returned client."""
        mock_factory = Mock(return_value=mock_auth0)

        provisioner = AuthZeroUserProvisioner(
            das_user_username="testuser",
            das_user_email="testuser@example.com",
            das_site_name="foo",
            auth0_organization_id="some-org-id",
            client_factory=mock_factory,
        )

        mock_factory.assert_called_once()
        assert provisioner.auth0 is mock_auth0
        assert provisioner.auth0_organization_id == "some-org-id"
        assert provisioner.connection_name == "test-connection"
        assert provisioner.das_user_username == "testuser"

    @pytest.mark.parametrize(
        ("das_user_email", "expected_auth0_user_email"),
        [("testuser@example.com", "testuser@example.com"), (None, "testuser.foo@managed.pamdas.org")],
    )
    def test_provision_user_success(self, mock_auth0, das_user_email, expected_auth0_user_email):
        """Test provision_user method creates user with correct parameters."""
        provisioner = AuthZeroUserProvisioner(
            das_user_username="testuser",
            das_user_email=das_user_email,
            das_site_name="foo",
            auth0_organization_id="some-org-id",
            client_factory=lambda: mock_auth0,
        )

        result = provisioner.provision_user()

        mock_auth0.users.create.assert_called_once_with(
            connection="test-connection",
            password="test-generated-password-123",
            username="testuser",
            email=expected_auth0_user_email,
        )

        mock_auth0.users.list.assert_called_once_with(
            q='username:"testuser" AND identities.connection:"test-connection"',
            include_totals=False,
            fields="user_id",
        )

        mock_auth0.organizations.members.create.assert_called_once_with("some-org-id", members=["auth0|123456789"])

        mock_auth0.tickets.change_password.assert_called_once_with(user_id="auth0|123456789")

        assert result == AuthZeroUserProvisioningResult(auth0_id="auth0|123456789", password_reset_link="some-url")

    def test_provision_user_user_already_exists(self, provisioner_test_instance, mock_auth0, caplog):
        """Test provision_user method logs warning when user already exists (409 error)."""
        mock_auth0.users.create.side_effect = ConflictError(body={})

        result = provisioner_test_instance.provision_user()

        assert "User 'testuser' already exists in Auth0" in caplog.text
        assert result == AuthZeroUserProvisioningResult(auth0_id="auth0|123456789", password_reset_link=None)

        mock_auth0.tickets.change_password.assert_not_called()

    def test_provision_user_other_create_error(self, provisioner_test_instance, mock_auth0):
        """Test provision_user method raises exception for non-409 API errors when creating."""
        mock_auth0.users.create.side_effect = ApiError(status_code=400, body={})

        with pytest.raises(ApiError):
            provisioner_test_instance.provision_user()

    def test_provision_user_id_retries_get_succeeds_on_second_attempt(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username succeeds on retry after initial failure."""
        mock_auth0.users.list.side_effect = [[], [Mock(user_id="auth0|123456789")]]

        result = provisioner_test_instance.provision_user()

        assert result == AuthZeroUserProvisioningResult(auth0_id="auth0|123456789", password_reset_link="some-url")

    def test_get_user_id_retries_get_exhausted_after_max_attempts(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username raises ValueError after exhausting retries."""
        mock_auth0.users.list.return_value = []

        with pytest.raises(ValueError, match="User 'testuser' not found in Auth0 connection 'test-connection'"):
            provisioner_test_instance._get_auth0_user_id_by_username()

    def test_get_user_id_retry_with_multiple_users_error(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username retries on multiple users ValueError."""
        mock_auth0.users.list.return_value = [Mock(user_id="auth0|123456789"), Mock(user_id="auth0|987654321")]

        with pytest.raises(
            ValueError, match="Multiple users found with username 'testuser' in Auth0 connection 'test-connection'"
        ):
            provisioner_test_instance._get_auth0_user_id_by_username()

    def test_get_user_id_raises_when_user_id_is_none(self, provisioner_test_instance, mock_auth0):
        """Test _get_auth0_user_id_by_username raises ValueError when API returns None user_id."""
        mock_auth0.users.list.return_value = [Mock(user_id=None)]

        with pytest.raises(ValueError, match="Expected non-None value for 'user_id'"):
            provisioner_test_instance._get_auth0_user_id_by_username()
