from datetime import datetime, timedelta, timezone

import pytest

from django.db import transaction
from django.test import override_settings
from django.urls import resolve, reverse
from rest_framework import status

from observations.models import SourceProvider
from observations.servicesutils import get_source_provider_statuses
from sensors.views import RadioAgentHandlerView


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDasRadioAgentHandler:
    PROVIDER_KEY = "dasradioagent"

    def test_url_handler(self):
        resolver = resolve(f"/api/v1.0/sensors/dasradioagent/{self.PROVIDER_KEY}/status/")
        assert resolver.func.cls == RadioAgentHandlerView

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_invalid_services_in_status(self, user_client):
        initial_services = get_source_provider_statuses()

        status_data = {"message_key": "heartbeat"}

        url = reverse("dasradioagenthandler", kwargs={"provider_key": str(self.PROVIDER_KEY)})
        response = user_client.post(url, data=status_data)

        assert response.status_code == status.HTTP_200_OK

        current_services = get_source_provider_statuses()

        # No new service key stored in redis
        assert len(initial_services) == len(current_services)

        # valid data from all preexistent keys
        assert all([all(k in r.keys() for k in ["heartbeat", "datasource"]) for r in current_services])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_services_in_status(self, user_client):
        # Create SourceProvider record first
        SourceProvider.objects.get_or_create(
            provider_key=self.PROVIDER_KEY, defaults={"display_name": "DAS Radio Agent"}
        )

        now = datetime.now(tz=timezone.utc)

        status_data = {
            "message_key": "heartbeat",
            "heartbeat": {
                "title": "System Activity",
                "interval": 15,
                "latest_at": now.isoformat(),
                "started_at": (now - timedelta(hours=4)).isoformat(),
                "uptime": "6 days 05:12:13",
            },
            "datasource": {
                "title": "Radio Activity",
                "connected": True,
                "connection_changed_at": now.isoformat(),
                "latest_at": now.isoformat(),
            },
        }

        url = reverse("dasradioagenthandler", kwargs={"provider_key": str(self.PROVIDER_KEY)})
        response = user_client.post(url, data=status_data)

        assert response.status_code == status.HTTP_200_OK

        with transaction.atomic():
            current_services = get_source_provider_statuses()

            # valid data from all preexistent keys
            assert all([all(k in r.keys() for k in ["heartbeat", "datasource"]) for r in current_services])
