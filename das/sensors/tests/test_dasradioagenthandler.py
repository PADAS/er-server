import json
from datetime import datetime, timedelta, timezone

from django.db import OperationalError, connections
from django.db.utils import InterfaceError
from django.urls import resolve
from rest_framework import status

from core.tests import BaseAPITest
from observations.servicesutils import get_source_provider_statuses
from sensors.handlers import DasRadioAgentHandler
from sensors.views import RadioAgentHandlerView


class DasRadioAgentHandlerTest(BaseAPITest):
    PROVIDER_KEY = "dasradioagent"

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
        request = self.factory.post(
            self.api_path, data=json.dumps({"message_key": "heartbeat"}), content_type="application/json"
        )

        self.force_authenticate(request, self.app_user)
        result = RadioAgentHandlerView.as_view()(request, self.PROVIDER_KEY)
        assert result.status_code == status.HTTP_200_OK

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
        request = self.factory.post(self.api_path, data=json.dumps(status_data), content_type="application/json")

        self.force_authenticate(request, self.app_user)
        result = RadioAgentHandlerView.as_view()(request, self.PROVIDER_KEY)
        assert result.status_code == status.HTTP_200_OK

        try:
            # theory is that request above left the db connection in a bad state
            # so we see the next test "test_url_handler" fail as well
            # the teardownClass cleans up connections, so the next test cases recover
            current_services = get_source_provider_statuses()
        except (OperationalError, InterfaceError):
            for conn in connections.all():
                conn.close_if_unusable_or_obsolete()
                conn.close()
                conn.connect()
            current_services = get_source_provider_statuses()

        # valid data from all preexistent keys
        self.assertTrue(all(k in r.keys() for k in ["heartbeat", "datasource"]) for r in current_services)
