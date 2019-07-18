import json
import copy
import datetime

from django.utils import timezone
from django.db import transaction

from rest_framework import status
from django.utils import lorem_ipsum

from core.tests import BaseAPITest
from sensors.views import SensorObservation
from observations.models import Subject, SourceProvider, Source, Observation, SubjectGroup, SubjectSubType
from unittest import mock

class GenericSensorHandlerTest(BaseAPITest):
    source_type = 'tracking-collar'
    sensor_type = 'ste-collar'
    provider = 'test_provider'
    manufacturer_id = "ST2010-3034"

    one_observation = {
        "subject_name": "test_subject",
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

        self.api_path = '/'.join((self.api_base, 'sensors',
                                  self.sensor_type, self.provider, 'status'))

    def run_transaction_hooks(self):
        """
        Mock transaction hooks to validate code for delayed on_commit functions.
        :return: None

        This supports validating a fix for https://vulcan.atlassian.net/browse/DAS-4052 whereby we didn't catch
        an invalid call to an on_commit handler. This Mock allows us "execute" our transaction on_commit code but
        without using TransactionTestCase which can be prohibitively slow.
        """
        for db_name in reversed(self._databases_names()):
            with mock.patch('django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block',
                            lambda a: False):
                transaction.get_connection(using=db_name).run_and_clear_commit_hooks()

    def tearDown(self):
        self.run_transaction_hooks()

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
        self.assertEqual(1, Observation.objects.filter(
            source=self.test_source).count())

    def test_post_with_additional(self):
        observation = copy.deepcopy(self.one_observation)
        observation.update(
            {"additional": {"event_action": "device_location_changed"}})
        response = self._post_data(json.dumps(observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source=self.test_source).count())

    def test_post_with_new_source_subject_subtype(self):
        observation = copy.deepcopy(self.one_observation)
        observation.update({"subject_subtype": "ranger"})
        observation['manufacturer_id'] = lorem_ipsum.words(2)
        observation['subject_name'] = lorem_ipsum.words(2)
        response = self._post_data(json.dumps(observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=Source.objects.get(
            manufacturer_id=observation['manufacturer_id'])).count())
        self.assertEqual(Subject.objects.get(
            name=observation['subject_name']).subject_subtype, SubjectSubType.objects.get(value="ranger"))

    def test_post_with_new_source_subject_groups(self):
        observation = copy.deepcopy(self.one_observation)
        observation.update({"subject_groups": ["sg_1", "sg_2"]})
        observation['manufacturer_id'] = lorem_ipsum.words(2)
        observation['subject_name'] = lorem_ipsum.words(2)
        response = self._post_data(json.dumps(observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, SubjectGroup.objects.filter(name="sg_2").count())
        self.assertIn(Subject.objects.get(
            name=observation['subject_name']), SubjectGroup.objects.get(name="sg_1").subjects.all())

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
        self.assertEqual(10, Observation.objects.filter(
            source__provider=self.test_sourceprovider).count())

    def test_post_multiple_batches(self):
        obs_list = [x for x in self._generate_observations(300, distinct=True)]
        response = self._post_data(json.dumps(obs_list))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(300, Observation.objects.count())

    def test_post_two_different_ids(self):
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        Source.objects.create(source_type=self.source_type,
                              provider=self.test_sourceprovider, manufacturer_id='mfg_id')
        local_obs = dict(self.one_observation)
        local_obs.update(manufacturer_id='mfg_id')
        response = self._post_data(json.dumps(local_obs))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(2, Observation.objects.filter(
            source__provider=self.test_sourceprovider).count())

    def test_post_one_request_two_srcs(self):
        Source.objects.create(source_type=self.source_type,
                              provider=self.test_sourceprovider, manufacturer_id='mfg_id')
        new_obs = dict(self.one_observation)
        new_obs.update(manufacturer_id='mfg_id')
        response = self._post_data(json.dumps([self.one_observation, new_obs]))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(2, Observation.objects.count())

    def _generate_observations(self, n=10, distinct=False):
        for i in range(n):
            obs = dict(self.one_observation)
            if distinct:
                timestamp = timezone.now() - datetime.timedelta(days=i)
                obs.update(recorded_at=timestamp.strftime("%Y-%m-%d %H:%M:%S"))

            yield obs

    def _post_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(
            request, sensor_type=self.sensor_type, provider_key=self.provider)
        return response
