from io import StringIO
from unittest.mock import patch

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from ..features import features


@pytest.mark.django_db
@pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
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
        tenant_settings,
    ):
        # Mock the tenant settings in TenantData
        tenant_data_mock.return_value.get.return_value = tenant_settings

        # Call the command
        out = StringIO()
        call_command("dummy_tenant_command", tenant_domain=tenant_model_instance.domain, stdout=out)
        # Check that the right methods are called to set the tenant instance and tenant settings in the current thread
        assert set_current_tenant_mock.called
        set_current_tenant_mock.assert_called_with(tenant=tenant_model_instance)
        assert tenant_data_mock.return_value.get.called
        assert set_tenant_settings_mock.called
        set_tenant_settings_mock.assert_called_with(value=tenant_settings)
        # Check that the handle method of the derived command class was called
        assert "dummy tenant-aware command executed." in out.getvalue()

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_call_tenant_command_in_verbose_mode(
        self,
        set_tenant_settings_mock,
        set_current_tenant_mock,
        tenant_data_mock,
        tenant_model_instance,
        tenant_settings,
    ):
        # Mock the tenant settings in TenantData
        tenant_data_mock.return_value.get.return_value = tenant_settings

        # Call the command
        out = StringIO()
        call_command("dummy_tenant_command", tenant_domain=tenant_model_instance.domain, verbosity=2, stdout=out)
        # Check that extra info about the tenant and settings is written to stdout
        assert f"Executing command with tenant id {tenant_model_instance.id} and tenant settings {tenant_settings}.."
        # Check that the handle method of the derived command class was called
        assert "dummy tenant-aware command executed." in out.getvalue()

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_tenant_domain_is_required(
        self, set_tenant_settings_mock, set_current_tenant_mock, tenant_model_instance, tenant_settings
    ):
        # Check that CommandError is raised if --tenant_domain isn't set
        with pytest.raises(CommandError):
            call_command("dummy_tenant_command")

    @patch("utils.tenant.commands.TenantData")
    @patch("utils.tenant.commands.set_current_tenant")
    @patch("utils.tenant.commands.set_tenant_settings")
    def test_raise_error_on_tenant_not_found(
        self, set_tenant_settings_mock, set_current_tenant_mock, tenant_model_instance, tenant_settings
    ):
        # Check that CommandError is raised if the domain doesn't match with a tenant
        with pytest.raises(CommandError):
            call_command("dummy_tenant_command", tenant_domain="notatenantdomain")
