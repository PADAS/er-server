from unittest.mock import patch

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from utils.features import features


@pytest.mark.django_db
@pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
class TestTenantBaseCommand:
    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_call_tenant_command_with_domain(
        self,
        set_tenant_settings_mock,
        set_current_tenant_mock,
        tenant_data_mock,
        das_tenant,
        tenant_response,
        capsys,
    ):
        tenant_data_mock.return_value.get_tenant_data.return_value = tenant_response

        call_command("dummy_tenant_command", tenant_domain=das_tenant.domain)
        captured = capsys.readouterr()

        set_current_tenant_mock.assert_called_once()
        set_current_tenant_mock.assert_called_with(tenant=das_tenant)
        tenant_data_mock.return_value.get_tenant_data.assert_called_once()
        set_tenant_settings_mock.assert_called_once()
        set_tenant_settings_mock.assert_called_with(value=tenant_response)
        assert "dummy tenant-aware command executed." in captured.out

    @patch("core.management.commands.dummy_tenant_command.get_tenant_settings")
    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_call_tenant_command_in_verbose_mode(
        self,
        set_tenant_settings_mock,
        set_current_tenant_mock,
        tenant_data_mock,
        get_tenant_settings_mock,
        das_tenant,
        tenant_response,
        tenant,
        capsys,
    ):
        tenant_data_mock.return_value.get_tenant_data.return_value = tenant_response
        get_tenant_settings_mock.return_value = tenant

        call_command("dummy_tenant_command", tenant_domain=das_tenant.domain, verbosity=2)
        captured = capsys.readouterr()
        expected_extra_details = f"Executing command with tenant id {das_tenant.id}..."

        get_tenant_settings_mock.assert_called_once()
        assert expected_extra_details in captured.out
        assert "dummy tenant-aware command executed." in captured.out

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_tenant_is_required(
        self, get_tenant_settings_mock, set_tenant_settings_mock, set_current_tenant_mock, das_tenant, tenant_response
    ):
        with pytest.raises(CommandError):
            call_command("dummy_tenant_command")

        get_tenant_settings_mock.assert_called_once()

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_raise_error_on_tenant_domain_not_found(
        self, set_tenant_settings_mock, set_current_tenant_mock, das_tenant, tenant_response
    ):
        with pytest.raises(CommandError):
            call_command("dummy_tenant_command", tenant_domain="notatenantdomain")

    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_get_tenant_from_thread(
        self, get_tenant_settings_mock, set_tenant_settings_mock, set_current_tenant_mock, das_tenant, tenant
    ):
        get_tenant_settings_mock.return_value = tenant

        call_command("dummy_tenant_command")

        get_tenant_settings_mock.assert_called_once()
        assert not set_tenant_settings_mock.called
        set_current_tenant_mock.assert_called_once()
        set_current_tenant_mock.assert_called_with(tenant=das_tenant)
