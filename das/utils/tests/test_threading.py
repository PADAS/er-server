import logging
from unittest.mock import MagicMock

import pytest

from django.urls import reverse

from utils.features import features
from utils.tenant.thread import Tenant, get_tenant_settings, set_tenant_settings


class TestThreadStorage:
    @pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
    def test_set_tenant_dict_settings_in_main_thread(self, tenant_response):
        set_tenant_settings(tenant_response)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert tenant_response == settings.to_dict()


@pytest.mark.django_db
class TestTenantLogging:
    @pytest.mark.skipif(features.tms.is_on() is False, reason="TMS feature flag is off")
    def test_assert_logging_when_tenant_is_getting_from_local_thread(
        self, event_type, superuser_client, monkeypatch, caplog, tenant_response
    ):
        mock = MagicMock(return_value=tenant_response)
        monkeypatch.setattr("core.tms.HTTPClient.get_tenant_data", mock)
        caplog.set_level(logging.INFO)
        url = reverse("events")

        superuser_client.post(
            url,
            {"title": "Event number five", "event_type": event_type.value},
        )

        tenant_name = tenant_response["name"]
        tenant_domain = tenant_response["domain"]

        assert f"Getting tenant {tenant_name} with domain {tenant_domain} on EventsView.dispatch" in caplog.text
        assert f"Getting tenant {tenant_name} with domain {tenant_domain} on EventsView.post" in caplog.text
        assert f"Getting tenant {tenant_name} with domain {tenant_domain} on signal of event_post_save"
        assert f"Getting tenant {tenant_name} with domain {tenant_domain} on EventSerializer.create"
