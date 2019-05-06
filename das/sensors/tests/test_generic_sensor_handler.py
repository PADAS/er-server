import json
from rest_framework import status

from core.tests import BaseAPITest
from sensors.views import SensorObservation
from observations.models import Subject, SourceProvider, Source, SubjectSource


class GenericSensorHandlerTest(BaseAPITest):
    source_type = 'tracking-collar'
    sensor_type = 'ste-collar'
    provider = 'test_provider'
    manufacturer_id = "ST2010-3034"

    one_observation = {
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2019-04-09 12:01:00",
        "location": {
            "lon": "31.19239",
            "lat": "-24.43071"},
    }

    def setUp(self):
        super().setUp()
        # setup db: create subject, source, provider, subjectsource

        self.test_subject = Subject.objects.create(name="test_subject")
        self.test_sourceprovider = SourceProvider.objects.create(
            display_name=self.provider, provider_key=self.provider)
        self.test_source = Source.objects.create(
            source_type=self.source_type, provider=self.test_sourceprovider,
            manufacturer_id=self.manufacturer_id)
        self.test_subjectsource = SubjectSource.objects.create(
            source=self.test_source, subject=self.test_subject)

        self. api_path = '/'.join((self.api_base, 'sensors', self.sensor_type, self.provider, 'status'))

    def post_data(self, payload):
        request = self.factory.post(self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        return SensorObservation.as_view()(request, sensor_type=self.sensor_type, provider_key=self.provider)

    def test_post_one_sample(self):
        response = self.post_data(json.dumps(self.one_observation))
        self.assertTrue(response.status_code, status.HTTP_201_CREATED)

    def test_post_with_additional(self):
        self.one_observation["additional"] = {
            "event_action": "device_location_changed"
        }
        response = self.post_data(json.dumps(self.one_observation))
        self.assertTrue(response.status_code, status.HTTP_201_CREATED)



