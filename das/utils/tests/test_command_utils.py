from unittest.mock import patch

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from ..features import features


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
        tenant_model_instance,
        tenant_response,
        capsys,
    ):
        tenant_data_mock.return_value.get_tenant_data.return_value = tenant_response

        call_command("dummy_tenant_command", tenant_domain=tenant_model_instance.domain)

        assert set_current_tenant_mock.called
        set_current_tenant_mock.assert_called_with(tenant=tenant_model_instance)
        assert tenant_data_mock.return_value.get_tenant_data.called
        assert set_tenant_settings_mock.called
        set_tenant_settings_mock.assert_called_with(value=tenant_response)
        captured = capsys.readouterr()
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
        tenant_model_instance,
        tenant_response,
        tenant,
        capsys,
    ):
        tenant_data_mock.return_value.get_tenant_data.return_value = tenant_response
        get_tenant_settings_mock.return_value = tenant

        call_command("dummy_tenant_command", tenant_domain=tenant_model_instance.domain, verbosity=2)

        assert get_tenant_settings_mock.called
        captured = capsys.readouterr()
        expected_extra_details = (
            f"Executing command with tenant id {tenant_model_instance.id} and tenant settings {tenant_response}..."
        )
        assert expected_extra_details in captured.out
        assert "dummy tenant-aware command executed." in captured.out

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_tenant_domain_is_required(
        self, set_tenant_settings_mock, set_current_tenant_mock, tenant_model_instance, tenant_response
    ):
        # Check that CommandError is raised if --tenant_domain isn't set
        with pytest.raises(CommandError):
            call_command("dummy_tenant_command")

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_raise_error_on_tenant_not_found(
        self, set_tenant_settings_mock, set_current_tenant_mock, tenant_model_instance, tenant_response
    ):
        # Check that CommandError is raised if the domain doesn't match with a tenant
        with pytest.raises(CommandError):
            call_command("dummy_tenant_command", tenant_domain="notatenantdomain")
