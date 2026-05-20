from __future__ import annotations

from io import StringIO
from unittest.mock import ANY, Mock, patch

import pytest

from django.core.management import CommandError

from accounts.management.commands.upsert_das_users_to_auth0 import Command
from accounts.models import User
from utils.auth0.client import AuthZeroUserProvisioningResult


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUpsertDasUsersToAuth0Command:
    @pytest.fixture(autouse=True)
    def mock_tenant_settings(self):
        """Mock tenant settings with Auth0 organization ID."""
        mock_feature_flags = Mock()
        mock_feature_flags.idp_org_id = "test-auth0-org-123"

        mock_settings = Mock()
        mock_settings.feature_flags = mock_feature_flags
        mock_settings.domain = "testsite.example.org"

        with patch("accounts.management.commands.upsert_das_users_to_auth0.get_tenant_settings") as mock_get:
            mock_get.return_value = mock_settings
            yield mock_settings

    @pytest.fixture
    def mock_provisioner_factory(self, mock_provisioner):
        """Mock factory that returns our mock provisioner."""
        return Mock(return_value=mock_provisioner)

    @pytest.fixture
    def mock_provisioner(self):
        """Mock AuthZeroUserProvisioner."""
        return Mock()

    @pytest.fixture
    def mock_stdout(self):
        """Mock stdout of AuthZeroUserProvisioner."""
        return StringIO()

    @pytest.fixture
    def command_for_test(self, mock_provisioner_factory, mock_stdout):
        """Create Command instance with mocked dependencies for testing."""
        return Command(
            provisioner_factory=mock_provisioner_factory,
            stdout=mock_stdout,
        )

    def test_handle_raises_command_error_when_idp_org_id_is_none(self, mock_tenant_settings):
        """Test that handle raises CommandError when idp_org_id is None."""
        mock_feature_flags = Mock()
        mock_feature_flags.idp_org_id = None

        mock_tenant_settings.feature_flags = mock_feature_flags

        command = Command(provisioner_factory=Mock())

        with pytest.raises(CommandError, match="idp_org_id is not configured in tenant feature flags"):
            command.handle()

    @pytest.mark.parametrize("bad_domain", ["not a domain", "pamdas.org", "https://pamdas.org", "site.pamdas"])
    def test_handle_raises_command_error_when_site_domain_not_good(self, mock_tenant_settings, bad_domain):
        """Test that handle raises CommandError when domain cannot be converted to site."""
        mock_tenant_settings.domain = bad_domain

        command = Command(provisioner_factory=Mock())

        with pytest.raises(
            CommandError,
            match=f"Cannot extract site name from {bad_domain}",
        ):
            command.handle()

    @pytest.mark.parametrize(
        "valid_domain,expected_site",
        [
            ("demo.pamdas.org", "demo"),
            ("demo.dev.pamdas.org", "demo"),
            ("some.long.subdomain.pamdas.org", "some"),
            ("another.example.com", "another"),
        ],
    )
    def test_handle_parses_valid_domains_successfully(
        self,
        mock_tenant_settings,
        mock_provisioner,
        mock_provisioner_factory,
        command_for_test,
        valid_domain,
        expected_site,
    ):
        """Test that handle successfully parses valid domains and extracts correct site names."""
        mock_tenant_settings.domain = valid_domain

        User.objects.create_user(
            username="test-user",
            email="test-user@example.com",
            password="test-password-123",
            is_active=True,
        )

        mock_provisioner.provision_user.return_value = AuthZeroUserProvisioningResult(
            auth0_id="auth0|new-user-123", password_reset_link=""
        )

        command_for_test.handle()

        mock_provisioner_factory.assert_called_once_with(
            das_user_username=ANY,
            das_user_email=ANY,
            das_site_name=expected_site,
            auth0_organization_id=ANY,
        )

    def test_new_user_gets_provisioned_and_saved(
        self,
        mock_provisioner_factory,
        mock_provisioner,
        mock_stdout,
        mock_tenant_settings,
        command_for_test,
    ):
        """Test that new user gets provisioned in Auth0 and their ID is saved to database."""
        User.objects.create_user(
            username="test-user",
            email="test-user@example.com",
            password="test-password-123",
            is_active=True,
        )

        mock_provisioner.provision_user.return_value = AuthZeroUserProvisioningResult(
            auth0_id="auth0|new-user-123", password_reset_link="https://auth0.example.com/reset-password?token=abc123"
        )

        command_for_test.handle()

        mock_provisioner_factory.assert_called_once_with(
            das_user_username="test-user",
            das_user_email="test-user@example.com",
            das_site_name="testsite",
            auth0_organization_id=mock_tenant_settings.feature_flags.idp_org_id,
        )

        test_user = User.objects.get(username="test-user")
        assert test_user.auth0_id == "auth0|new-user-123"

        output = mock_stdout.getvalue()
        expected_output = """SUCCESSFULLY PROVISIONED:
test-user\thttps://auth0.example.com/reset-password?token=abc123
"""
        assert output == expected_output

    def test_existing_user_gets_provisioned_and_no_change(
        self,
        mock_provisioner_factory,
        mock_provisioner,
        mock_stdout,
        mock_tenant_settings,
        command_for_test,
    ):
        """Test that existing user gets provisioned in Auth0 and their ID is unchanged."""
        User.objects.create_user(
            username="test-user",
            email="test-user@example.com",
            password="test-password-123",
            is_active=True,
            auth0_id="auth0|existing-user-123",
        )

        mock_provisioner.provision_user.return_value = AuthZeroUserProvisioningResult(
            auth0_id="auth0|existing-user-123", password_reset_link=None
        )

        command_for_test.handle()

        mock_provisioner_factory.assert_called_once_with(
            das_user_username="test-user",
            das_user_email="test-user@example.com",
            das_site_name="testsite",
            auth0_organization_id=mock_tenant_settings.feature_flags.idp_org_id,
        )

        test_user = User.objects.get(username="test-user")
        assert test_user.auth0_id == "auth0|existing-user-123"

        output = mock_stdout.getvalue()
        expected_output = """SUCCESSFULLY PROVISIONED:
test-user\tNone
"""
        assert output == expected_output

    def test_existing_user_with_id_conflict_fails(
        self,
        mock_provisioner_factory,
        mock_provisioner,
        mock_stdout,
        mock_tenant_settings,
        command_for_test,
    ):
        """Test that existing user gets provisioned in Auth0 and an id conflict is handled."""
        User.objects.create_user(
            username="test-user",
            email="test-user@example.com",
            password="test-password-123",
            is_active=True,
            auth0_id="auth0|existing-user-123",
        )

        mock_provisioner.provision_user.return_value = AuthZeroUserProvisioningResult(
            auth0_id="auth0|mismatched-id", password_reset_link=None
        )

        with pytest.raises(CommandError) as exc_info:
            command_for_test.handle()

        error_message = str(exc_info.value)
        assert "Failed to provision 1 users!" in error_message

        mock_provisioner_factory.assert_called_once_with(
            das_user_username="test-user",
            das_user_email="test-user@example.com",
            das_site_name="testsite",
            auth0_organization_id=mock_tenant_settings.feature_flags.idp_org_id,
        )

        test_user = User.objects.get(username="test-user")
        assert test_user.auth0_id == "auth0|existing-user-123"

        output = mock_stdout.getvalue()
        expected_output = """FAILED TO PROVISION:
test-user\tUser test-user already has auth0_id 'auth0|existing-user-123' but Auth0 returned 'auth0|mismatched-id'
"""
        assert output == expected_output

    def test_disallowed_usernames_are_omitted(
        self,
        mock_provisioner_factory,
        mock_provisioner,
        mock_stdout,
        mock_tenant_settings,
        command_for_test,
    ):
        """Test that disallowed usernames are filtered out and not provisioned to Auth0."""
        User.objects.create_user(
            username="er_system",
            email="er_system@example.com",
            password="test-password-123",
            is_active=True,
        )
        User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
            is_active=True,
        )

        command_for_test.handle()

        mock_provisioner_factory.assert_not_called()
        mock_provisioner.provision_user.assert_not_called()

        output = mock_stdout.getvalue()
        assert output == ""

    def test_multiple_users_with_mixed_outcomes(
        self,
        mock_provisioner_factory,
        mock_provisioner,
        mock_stdout,
        mock_tenant_settings,
        command_for_test,
    ):
        """Test complex behavior and outputs."""
        User.objects.create_user(
            username="first-new-user",
            email="first-new-user@example.com",
            password="test-password-123",
            is_active=True,
        )
        User.objects.create_user(
            username="second-new-user",
            email="second-new-user@example.com",
            password="test-password-123",
            is_active=True,
        )
        User.objects.create_user(
            username="emailless-user",
            password="test-password-123",
            is_active=True,
        )
        User.objects.create_user(
            username="inactive-user",
            email="inactive-user@example.com",
            password="test-password-123",
            is_active=False,
        )
        User.objects.create_user(
            username="existing-user-with-matching-id",
            email="existing-user-with-matching-id@example.com",
            password="test-password-123",
            is_active=True,
            auth0_id="auth0|some-id",
        )
        User.objects.create_user(
            username="existing-user-conflicting-id",
            email="existing-user-with-conflicting-id@example.com",
            password="test-password-123",
            is_active=True,
            auth0_id="auth0|an-unexpected-id",
        )
        User.objects.create_user(
            username="er_system",
            email="er_system@example.com",
            password="test-password-123",
            is_active=True,
        )
        User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
            is_active=True,
        )

        per_user_results = {
            "first-new-user": AuthZeroUserProvisioningResult(
                auth0_id="auth0|new-id-1", password_reset_link="https://reset1.example.com"
            ),
            "second-new-user": AuthZeroUserProvisioningResult(
                auth0_id="auth0|new-id-2", password_reset_link="https://reset2.example.com"
            ),
            "emailless-user": AuthZeroUserProvisioningResult(
                auth0_id="auth0|new-id-3", password_reset_link="https://reset3.example.com"
            ),
            "existing-user-with-matching-id": AuthZeroUserProvisioningResult(
                auth0_id="auth0|some-id", password_reset_link=None
            ),
            "existing-user-conflicting-id": AuthZeroUserProvisioningResult(
                auth0_id="auth0|a-different-id-than-what-we-expect", password_reset_link=None
            ),
        }
        # The factory is always called immediately before provision_user(), so call_args reflects the current user.
        mock_provisioner.provision_user.side_effect = lambda: per_user_results[
            mock_provisioner_factory.call_args.kwargs["das_user_username"]
        ]

        with pytest.raises(CommandError) as exc_info:
            command_for_test.handle()

        first_user = User.objects.get(username="first-new-user")
        assert first_user.auth0_id == "auth0|new-id-1"

        second_user = User.objects.get(username="second-new-user")
        assert second_user.auth0_id == "auth0|new-id-2"

        emailless_user = User.objects.get(username="emailless-user")
        assert emailless_user.auth0_id == "auth0|new-id-3"

        existing_user = User.objects.get(username="existing-user-with-matching-id")
        assert existing_user.auth0_id == "auth0|some-id"

        conflicting_user = User.objects.get(username="existing-user-conflicting-id")
        assert conflicting_user.auth0_id == "auth0|an-unexpected-id"

        assert mock_provisioner.provision_user.call_count == 5

        output_lines = mock_stdout.getvalue().splitlines()
        success_header = output_lines.index("SUCCESSFULLY PROVISIONED:")
        failure_header = output_lines.index("FAILED TO PROVISION:")
        assert success_header < failure_header
        success_lines = set(output_lines[success_header + 1 : failure_header])
        failure_lines = set(output_lines[failure_header + 1 :])

        assert success_lines == {
            "first-new-user\thttps://reset1.example.com",
            "second-new-user\thttps://reset2.example.com",
            "emailless-user\thttps://reset3.example.com",
            "existing-user-with-matching-id\tNone",
        }
        assert failure_lines == {
            "existing-user-conflicting-id\tUser existing-user-conflicting-id already has auth0_id 'auth0|an-unexpected-id' but Auth0 returned 'auth0|a-different-id-than-what-we-expect'",
        }

        error_message = str(exc_info.value)
        assert "Failed to provision 1 users!" in error_message
