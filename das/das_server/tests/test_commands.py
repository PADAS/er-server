from unittest.mock import MagicMock, patch

import pytest

from django.core.management import call_command

from das.utils.features import features


@pytest.mark.django_db
@pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
class TestCommands:
    @patch("utils.tenant.commands.set_tenant")
    @patch("utils.tenant.commands.get_current_tenant")
    @patch("utils.tenant.commands.get_tenant_settings")
    def test_call_site_metrics(
        self,
        set_tenant_settings_mock,
        set_current_tenant_mock,
        tenant_data_mock,
        das_tenant,
        tenant_response,
        monkeypatch,
    ):
        site_metrics_mock = MagicMock(return_value=None)
        monkeypatch.setattr("das_server.management.commands.site_metrics.Command.handle", site_metrics_mock)

        call_command("site_metrics", tenant_domain=das_tenant.domain)

        site_metrics_mock.assert_called_once()
