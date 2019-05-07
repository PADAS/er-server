import json
import datetime
from django.utils import timezone
from rest_framework import status

from core.tests import BaseAPITest
from sensors.views import SensorObservation
from observations.models import Subject, SourceProvider, Source, Observation


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

        # setup db: create subject, source, provider
        Subject.objects.create(name="test_subject")
        self.test_sourceprovider = SourceProvider.objects.create(
            display_name=self.provider, provider_key=self.provider)
        self.test_source = Source.objects.create(
            source_type=self.source_type, provider=self.test_sourceprovider,
            manufacturer_id=self.manufacturer_id)

        self.api_path = '/'.join((self.api_base, 'sensors', self.sensor_type, self.provider, 'status'))

    def test_badrequest_manufacturer_id_missing(self):
        local_obs = dict(self.one_observation)
        local_obs.pop("manufacturer_id", None)
        response = self._post_data(json.dumps(local_obs))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_badrequest_recorded_at_missing(self):
        local_obs = dict(self.one_observation)
        local_obs.pop('recorded_at', None)
        response = self._post_data(json.dumps(local_obs))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_badrequest_location_missing(self):
        local_obs = dict(self.one_observation)
        local_obs.pop("location", None)
        response = self._post_data(json.dumps(local_obs))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_one(self):
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=self.test_source).count())

    def test_post_with_additional(self):
        self.one_observation.update({"additional": {"event_action": "device_location_changed"}})
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=self.test_source).count())

    def test_post_ten_has_dups(self):
        obs_list = [x for x in self._generate_observations()]

        response = self._post_data(json.dumps(obs_list))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source__provider=self.test_sourceprovider, source=self.test_source).count())

    def test_post_ten(self):
        obs_list = [x for x in self._generate_observations(distinct=True)]

        response = self._post_data(json.dumps(obs_list))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(10, Observation.objects.filter(source__provider=self.test_sourceprovider).count())

    def test_post_two_different_ids(self):
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        Source.objects.create(source_type=self.source_type, provider=self.test_sourceprovider, manufacturer_id='mfg_id')
        local_obs = dict(self.one_observation)
        local_obs.update(manufacturer_id='mfg_id')
        response = self._post_data(json.dumps(local_obs))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(2, Observation.objects.filter(source__provider=self.test_sourceprovider).count())

    def _generate_observations(self, n=10, distinct=False):
        for i in range(n):
            obs = dict(self.one_observation)
            if distinct:
                timestamp = timezone.now() - datetime.timedelta(days=i)
                obs.update(recorded_at=timestamp.strftime("%Y-%m-%d %H:%M:%S"))

            yield obs

    def _post_data(self, payload):
        request = self.factory.post(self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(request, sensor_type=self.sensor_type, provider_key=self.provider)
        return response


