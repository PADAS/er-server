from datetime import datetime, timedelta, timezone

import pytest

from django.urls import resolve, reverse
from rest_framework import status

from core.tests import BaseAPITest
from observations.servicesutils import get_source_provider_statuses
from sensors.handlers import DasRadioAgentHandler
from sensors.views import RadioAgentHandlerView


class DasRadioAgentHandlerTest(BaseAPITest):
    PROVIDER_KEY = "dasradioagent"

    @pytest.fixture(autouse=True)
    def inject_fixtures(self, request):
        # Access the fixture using request.getfixturevalue
        self.user_client = request.getfixturevalue("user_client")

    def setUp(self):
        super().setUp()
        self.api_path = "/".join(
            (self.api_base, "sensors", DasRadioAgentHandler.SENSOR_TYPE, self.PROVIDER_KEY, "status")
        )

    def test_url_handler(self):
        resolver = resolve(self.api_path + "/")
        assert resolver.func.cls == RadioAgentHandlerView

    def test_invalid_services_in_status(self):
        initial_services = get_source_provider_statuses()

        status_data = {"message_key": "heartbeat"}

        url = reverse("dasradioagenthandler", kwargs={"provider_key": str(self.PROVIDER_KEY)})
        response = self.user_client.post(url, data=status_data)

        assert response.status_code == status.HTTP_200_OK

        current_services = get_source_provider_statuses()

        # No new service key stored in redis
        self.assertEqual(len(initial_services), len(current_services))

        # valid data from all preexistent keys
        self.assertTrue(all(k in r.keys() for k in ["heartbeat", "datasource"]) for r in current_services)

    def test_services_in_status(self):
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
        response = self.user_client.post(url, data=status_data)

        assert response.status_code == status.HTTP_200_OK

        current_services = get_source_provider_statuses()

        # valid data from all preexistent keys
        self.assertTrue(all(k in r.keys() for k in ["heartbeat", "datasource"]) for r in current_services)
