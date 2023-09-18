from unittest.mock import patch

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from utils.features import features
from utils.tenant.exceptions import (
    TenantNotFoundException,
    TenantNotFoundInLocalThreadException,
)


@pytest.mark.django_db
@pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
class TestTenantBaseCommand:
    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_call_tenant_command_with_domain(
        self,
        get_tenant_settings_mock,
        get_current_tenant_mock,
        set_tenant_mock,
        das_tenant,
        capsys,
    ):
        get_tenant_settings_mock.side_effect = TenantNotFoundInLocalThreadException
        get_current_tenant_mock.return_value = None

        call_command("dummy_tenant_command", tenant_domain=das_tenant.domain)
        captured = capsys.readouterr()

        set_tenant_mock.assert_called_once()
        set_tenant_mock.assert_called_with(domain=das_tenant.domain)
        assert not get_current_tenant_mock.called
        assert not get_tenant_settings_mock.called
        assert "dummy tenant-aware command executed." in captured.out

    @patch("core.management.commands.dummy_tenant_command.get_current_tenant")
    @patch("core.management.commands.dummy_tenant_command.get_tenant_settings")
    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_call_tenant_command_in_verbose_mode(
        self,
        get_tenant_settings_mock,
        get_current_tenant_mock,
        set_tenant_mock,
        dummy_command_tenant_settings_mock,
        dummy_command_current_tenant_mock,
        das_tenant,
        tenant,
        capsys,
    ):
        # Simulate no tenant is set on thread
        get_current_tenant_mock.return_value = None
        get_tenant_settings_mock.return_value = tenant
        dummy_command_tenant_settings_mock.return_value = tenant
        dummy_command_current_tenant_mock.return_value = das_tenant

        call_command("dummy_tenant_command", tenant_domain=das_tenant.domain, verbosity=2)
        captured = capsys.readouterr()
        expected_extra_details = f"Executing command with tenant id {das_tenant.id}..."

        set_tenant_mock.assert_called_once()
        set_tenant_mock.assert_called_with(domain=das_tenant.domain)
        assert not get_current_tenant_mock.called
        get_tenant_settings_mock.assert_called_once()
        dummy_command_tenant_settings_mock.assert_called_once()
        dummy_command_current_tenant_mock.assert_called_once()
        assert expected_extra_details in captured.out
        assert "dummy tenant-aware command executed." in captured.out

    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_tenant_is_required(
        self,
        get_tenant_settings_mock,
        get_current_tenant_mock,
        set_tenant_mock,
        das_tenant,
        tenant,
    ):
        # Simulate no tenant is set on thread
        get_tenant_settings_mock.side_effect = TenantNotFoundInLocalThreadException
        get_current_tenant_mock.return_value = None

        with pytest.raises(CommandError):
            call_command("dummy_tenant_command")  # No domain is specified

        assert not set_tenant_mock.called
        get_tenant_settings_mock.assert_called_once()
        get_current_tenant_mock.assert_called_once()

    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_raise_error_on_tenant_domain_not_found(
        self,
        get_tenant_settings_mock,
        get_current_tenant_mock,
        set_tenant_mock,
        das_tenant,
        tenant,
    ):
        # Simulate no tenant is set on thread
        get_tenant_settings_mock.side_effect = TenantNotFoundInLocalThreadException
        get_current_tenant_mock.return_value = None
        set_tenant_mock.side_effect = TenantNotFoundException
        wrong_domain = "notatenantdomain"

        with pytest.raises(CommandError):
            call_command("dummy_tenant_command", tenant_domain=wrong_domain)

        assert set_tenant_mock.called_once
        set_tenant_mock.assert_called_with(domain=wrong_domain)

    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.post_tenant_to_thread")
    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_get_tenant_from_tenant_obj_in_thread(
        self,
        get_tenant_settings_mock,
        get_current_tenant_mock,
        set_tenant_mock,
        post_tenant_to_thread_mock,
        set_current_tenant_mock,
        das_tenant,
        tenant,
        capsys,
    ):
        get_tenant_settings_mock.return_value = tenant
        get_current_tenant_mock.return_value = None

        call_command("dummy_tenant_command")

        get_tenant_settings_mock.assert_called_once()
        set_current_tenant_mock.assert_called_once()
        set_current_tenant_mock.assert_called_with(tenant=das_tenant)
        assert not set_tenant_mock.called
        assert not post_tenant_to_thread_mock.called

    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.post_tenant_to_thread")
    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_get_tenant_from_das_tenant_in_thread(
        self,
        get_tenant_settings_mock,
        get_current_tenant_mock,
        set_tenant_mock,
        post_tenant_to_thread_mock,
        set_current_tenant_mock,
        das_tenant,
        tenant,
    ):
        get_tenant_settings_mock.side_effect = TenantNotFoundInLocalThreadException
        get_current_tenant_mock.return_value = das_tenant

        call_command("dummy_tenant_command")

        get_tenant_settings_mock.assert_called_once()
        get_current_tenant_mock.assert_called_once()
        post_tenant_to_thread_mock.assert_called_once()
        post_tenant_to_thread_mock.assert_called_with(domain=das_tenant.domain)
        assert not set_tenant_mock.called
        assert not set_current_tenant_mock.called
