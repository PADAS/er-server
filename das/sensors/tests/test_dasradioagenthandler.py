
import json

from django.urls import resolve

from core.tests import BaseAPITest
from observations.servicesutils import get_source_provider_statuses
from sensors.handlers import DasRadioAgentHandler
from sensors.views import RadioAgentHandlerView


class DasRadioAgentHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'dasradioagent'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  DasRadioAgentHandler.SENSOR_TYPE,
                                  self.PROVIDER_KEY, 'status'))

    def test_url_handler(self):
        resolver = resolve(self.api_path + "/")
        assert resolver.func.cls == RadioAgentHandlerView

    def test_invalid_services_in_status(self):
        initial_services = get_source_provider_statuses()
        request = self.factory.post(
            self.api_path, data=json.dumps({'message_key': 'heartbeat'}), content_type='application/json')

        self.force_authenticate(request, self.app_user)
        RadioAgentHandlerView.as_view()(request, self.PROVIDER_KEY)
        current_services = get_source_provider_statuses()

        # No new service key stored in redis
        self.assertEqual(len(initial_services), len(current_services))

        # valid data from all preexistent keys
        self.assertTrue(all(k in r.keys() for k in [
                        'heartbeat', 'datasource']) for r in current_services)
