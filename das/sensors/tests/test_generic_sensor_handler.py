import copy
import datetime
import json
from unittest import mock
from uuid import uuid4

import pytz
from dateutil import parser as dateparser

import django.contrib.auth
from django.db import transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import lorem_ipsum
from rest_framework import status

from core.tests import BaseAPITest, fake_get_pool
from observations.models import (Observation, Source, SourceProvider, Subject,
                                 SubjectGroup, SubjectSubType)
from sensors.views import GenericSensorHandlerView

User = django.contrib.auth.get_user_model()


class GenericSensorHandlerTest(BaseAPITest):
    source_type = 'tracking-collar'
    sensor_type = 'ste-collar'
    provider = lorem_ipsum.words(100).replace(" ", "")[:100]
    manufacturer_id = "ST2010-3034"

    one_observation = {
        "subject_name": "test_subject",
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2019-04-09T12:01:00",
        "location": {
            "lon": "31.19239",
            "lat": "-24.43071"},
    }

    second_observation = {
        "subject_name": "test_subject",
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2020-03-07T16:28:38+00:00",
        "location": {
            "lon": "31.19239",
            "lat": "-24.43071"},
    }

    third_observation = {
        "location": {
            "lat": -24.33982,
            "lon": 32.29395
        },
        "recorded_at": "2019-11-25T14:59:25.0000000Z",
        "manufacturer_id": "1025",
        "subject_name": "administrator1025",
        "subject_type": "person",
        "subject_subtype": "ranger",
        "subject_groups": [
            "", ""
        ],
        "model_name": "dasradioagent:hytera",
        "source_type": "gps-radio",
        "message_key": "observation",
        "additional": {
            "event_action": "device_state_changed",
            "radio_state": "na",
            "radio_state_at": "2020-02-05T21:30:26.0946916Z",
            "last_voice_call_start_at": "2020-01-21T05:27:26.0000000Z"
        }
    }

    additional_observation = {
        "subject_name": "test_subject_w_additional",
        "subject_additional": {"sex": "male"},
        "source_additional": {"description": lorem_ipsum.words(2)},
        "manufacturer_id": "test_subject_w_additional_manufacturer_id",
        "recorded_at": "2020-03-07T16:28:38+00:00",
        "location": {
            "lon": "31.19239",
            "lat": "-24.43071"},
        "additional": {"temp": 40.1}
    }

    def setUp(self):
        super().setUp()

        user_const = dict(last_name='last', first_name='first')
        self.super_user = User.objects.create_superuser(
            'super_user', 'das_super_user@vulcan.com', 'super_user_pass',
            **user_const)

        # setup db: create subject, source, provider
        Subject.objects.create(name="test_subject")
        self.test_sourceprovider = SourceProvider.objects.create(
            display_name=self.provider, provider_key=self.provider)
        self.test_source = Source.objects.create(
            source_type=self.source_type, provider=self.test_sourceprovider,
            manufacturer_id=self.manufacturer_id)

        self.api_path = '/'.join((self.api_base, 'sensors',
                                  self.sensor_type, self.provider, 'status/'))

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
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
                transaction.get_connection(
                    using=db_name).run_and_clear_commit_hooks()

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

    @override_settings(SHOW_TRACK_DAYS=365)
    def test_post_one(self):
        """If the subject has only a couple of observations and they are over a year old
        we shouldn't see tracks available and we shouldn't see the last_position field
        filled out with the default SubjectStatus placeholder record.
        """
        recorded_at_iso = self.one_observation['recorded_at']
        recorded_at = dateparser.parse(recorded_at_iso)
        self.assertEqual(recorded_at_iso, recorded_at.isoformat())

        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source=self.test_source).count())
        obs = next(iter(Observation.objects.filter(
            source=self.test_source)))

        # check subjectstatus.
        client = Client()
        client.force_login(self.super_user)
        response = client.get(
            reverse("subjects-list-view") + "?updated_since=2019-01-01")
        assert response.status_code == 200
        first_subject = response.data[0]
        assert not first_subject["tracks_available"]
        assert "last_position" not in first_subject
        assert "last_position_date" not in first_subject

    def test_request_recorded_at_timezone(self):
        recorded_at_iso = self.second_observation['recorded_at']
        recorded_at = dateparser.parse(recorded_at_iso)
        self.assertEqual(recorded_at_iso, recorded_at.isoformat())
        response = self._post_data(json.dumps(self.second_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        obs = next(iter(Observation.objects.filter(
            source=self.test_source)))
        self.assertEqual(recorded_at, obs.recorded_at)

    def test_request_subject_additional(self):
        response = self._post_data(json.dumps(self.additional_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        assert Subject.objects.get(
            name=self.additional_observation['subject_name']).additional['sex'] == 'male'

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

    def test_post_with_new_source_but_empty_subject_groups(self):
        observation = copy.deepcopy(self.one_observation)
        observation.update({"subject_groups": [""]})
        observation['manufacturer_id'] = lorem_ipsum.words(2)
        observation['subject_name'] = lorem_ipsum.words(2)
        response = self._post_data(json.dumps(observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(Subject.objects.get(
            name=observation['subject_name']), SubjectGroup.objects.get_default().subjects.all())

    def test_post_with_new_source_but_empty_subject_groups_two(self):
        self.third_observation['subject_groups'] = ["", ""]
        response = self._post_data(json.dumps(self.third_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(Subject.objects.get(
            name="administrator1025"), SubjectGroup.objects.get_default().subjects.all())

    def test_post_sensor_data_with_provided_subject_groups(self):
        self.third_observation['subject_groups'] = ["Quails"]
        response = self._post_data(json.dumps(self.third_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(
            Subject.objects.get(name="administrator1025"),
            SubjectGroup.objects.get(name='Quails').subjects.all())

    def test_post_sensor_data_with_provided_source_additional(self):
        self.third_observation['source_additional'] = {"frequency": "123.5"}

        response = self._post_data(json.dumps(self.third_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue('frequency',
                        Subject.objects.get(name="administrator1025").source.additional)

    def test_post_ten_has_dups(self):
        obs_list = [x for x in self._generate_observations()]

        response = self._post_data(json.dumps(obs_list))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source__provider=self.test_sourceprovider, source=self.test_source).count())

    def test_post_a_dup(self):
        response = self._post_data(json.dumps(self.third_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self._post_data(json.dumps(self.third_observation))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_ten(self):
        obs_list = [x for x in self._generate_observations(distinct=True)]

        response = self._post_data(json.dumps(obs_list))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(10, Observation.objects.filter(
            source__provider=self.test_sourceprovider).count())

    def test_post_multiple_batches(self):
        obs_list = [x for x in self._generate_observations(300, distinct=True)]
        response = self._post_data(json.dumps(obs_list))
        self.assertEqual(response.status_code,
                         status.HTTP_201_CREATED, response.data)
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

    def test_subject_source_donot_exist(self):
        new_source_id = 'new_src_id'
        local_obs = copy.deepcopy(self.one_observation)
        local_obs['manufacturer_id'] = new_source_id
        local_obs.pop('subject_name', None)
        response = self._post_data(json.dumps(local_obs))
        source = Source.objects.get(manufacturer_id=new_source_id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(source)
        self.assertEqual(1, Observation.objects.filter(source=source).count())
        self.assertIsNotNone(Subject.objects.get(name=new_source_id))

    def test_source_doesnot_exist(self):
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['manufacturer_id'] = 'random_mfg_id'
        response = self._post_data(json.dumps(obs_copy))
        source = Source.objects.get(manufacturer_id='random_mfg_id')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=source).count())
        self.assertIsNotNone(source)

    def test_provider_doesnot_exist(self):
        response = self._post_data(json.dumps(
            self.one_observation), 'random_src_provider')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.count())
        self.assertIsNotNone(SourceProvider.objects.get(
            provider_key='random_src_provider'))

    def test_subject_src_provider_donot_exist(self):
        mfg_id = 'brew_new_mfg_id'
        provider_key = 'new_provider_key'
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy.pop('subject_name', None)
        obs_copy['manufacturer_id'] = mfg_id
        response = self._post_data(json.dumps(obs_copy), provider_key)
        src = Source.objects.get(manufacturer_id=mfg_id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=src).count())
        self.assertIsNotNone(
            SourceProvider.objects.get(provider_key=provider_key))
        self.assertIsNotNone(src)
        self.assertIsNotNone(Subject.objects.get(name=mfg_id))

    def test_with_new_subject_id_and_source(self):
        uuid = uuid4()
        new_source_id = 'new_src_id'
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_id'] = uuid.hex
        obs_copy['manufacturer_id'] = new_source_id
        response = self._post_data(json.dumps(obs_copy))
        new_source = Source.objects.get(manufacturer_id=new_source_id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(new_source)
        self.assertEqual(1, Observation.objects.filter(
            source=new_source).count())
        self.assertIsNotNone(Subject.objects.get(pk=uuid))

    def test_multiple_obs_with_new_subject_id_and_source(self):
        uuid = uuid4()
        new_source_id = 'new_src_id'
        obs_list = [x for x in self._generate_observations(distinct=True)]
        for o in obs_list:
            o['subject_id'] = uuid.hex
            o['manufacturer_id'] = new_source_id
        response = self._post_data(json.dumps(obs_list))
        new_source = Source.objects.get(manufacturer_id=new_source_id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(new_source)
        self.assertEqual(len(obs_list), Observation.objects.filter(
            source=new_source).count())
        self.assertIsNotNone(Subject.objects.get(pk=uuid))

    def test_with_multiple_subject_ids_new_source(self):
        uuids = [uuid4() for i in range(5)]
        new_source_id = 'new_src_id'
        obs_list = [x for x in self._generate_observations(5, distinct=True)]
        for i, obs in enumerate(obs_list):
            obs['subject_id'] = uuids[i].hex
            obs['manufacturer_id'] = new_source_id

        response = self._post_data(json.dumps(obs_list))
        new_source = Source.objects.get(manufacturer_id=new_source_id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(new_source)
        self.assertEqual(len(obs_list), Observation.objects.filter(
            source=new_source).count())

        # for uuid in uuids:
        #     self.assertIsNotNone(Subject.objects.get(pk=uuid))

    def test_with_subject_subtype(self):
        subject_subtype = 'animal-awesome'
        new_source_id = 'new_src_id'
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_subtype'] = subject_subtype
        obs_copy['manufacturer_id'] = new_source_id

        response = self._post_data(json.dumps(obs_copy))
        new_source = Source.objects.get(manufacturer_id=new_source_id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(new_source)
        self.assertEqual(1, Observation.objects.filter(
            source=new_source).count())
        self.assertIsNotNone(SubjectSubType.objects.get(value=subject_subtype))

    def test_request_with_varying_provider_key_lengths(self):
        client = Client()
        client.force_login(self.super_user)

        response = client.post(
            self.api_path, self.one_observation, content_type="application/json")

        self.assertEqual(response.resolver_match.func.cls,
                         GenericSensorHandlerView)
        assert response.status_code == 201

        provider = lorem_ipsum.words(200).replace(" ", "")[:200]
        url = '/'.join((self.api_base, 'sensors',
                        self.sensor_type, provider, 'status'))

        response = client.post(url, self.one_observation,
                               content_type="application/json")
        assert response.status_code == 404  # Not found

    def _generate_observations(self, n=10, distinct=False):
        for i in range(n):
            obs = dict(self.one_observation)
            if distinct:
                timestamp = pytz.utc.localize(
                    datetime.datetime.utcnow()) - datetime.timedelta(days=i)
                obs.update(recorded_at=timestamp.isoformat())

            yield obs

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def _post_data(self, payload, provider=None):
        if not provider:
            provider = self.provider

        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = GenericSensorHandlerView.as_view()(
            request, sensor_type=self.sensor_type, provider_key=provider)
        return response
