import copy
import datetime
import json
from unittest import mock

import pytz

from django.db import transaction
from django.test import override_settings
from django.urls import resolve
from rest_framework import status

from accounts.models import User
from core.tests import BaseAPITest, fake_get_pool
from observations.models import (Observation, Source, SourceProvider, Subject,
                                 SubjectSource, SubjectSubType, SubjectType)
from sensors.views import ERTrackHandlerView
from tracking.models.er_track import (CREATE_NEW, UPDATE_NAME,
                                      SourceProviderConfiguration)


class ErTrackHandlerTest(BaseAPITest):
    source_type = 'tracking-collar'
    sensor_type = 'ertrack'
    provider = 'test_provider'
    manufacturer_id = "ST2010-3034"

    one_observation = {
        "subject_name": "test_subject",
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2019-04-09T12:01:00Z",
        "location": {
            "lon": "31.19239",
            "lat": "-24.43071"},
    }

    second_observation = {
        "subject_name": "test_subject",
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2019-04-09T12:02:00Z",
        "location": {
            "lon": "31.19239",
            "lat": "-24.43071"},
    }

    def setUp(self):
        super().setUp()
        # setup db: create source, provider
        self.test_sourceprovider = SourceProvider.objects.create(
            display_name=self.provider, provider_key=self.provider)
        self.test_source = Source.objects.create(
            source_type=self.source_type, provider=self.test_sourceprovider,
            manufacturer_id=self.manufacturer_id)

        self.api_path = '/'.join((self.api_base, 'sensors',
                                  self.sensor_type, self.provider, 'status'))
        self.super_user = User.objects.create_superuser(username="superuser",
                                                        password="adfsfds32423",
                                                        email="super@user.com")
        self.config = SourceProviderConfiguration.objects.get(is_default=True)

    def test_url_handler(self):
        resolver = resolve(self.api_path + "/")
        assert resolver.func.cls == ERTrackHandlerView

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_a_duplicate_observation(self):
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_duplicate_in_a_batch_of_observations(self):
        response = self._post_data(json.dumps(
            [self.one_observation, self.one_observation, self.one_observation]))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self._post_data(json.dumps(
            [self.second_observation, self.one_observation, self.one_observation]))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_new_device_handling_with_create_new_config(self):
        config = self.config
        config.new_device_config = CREATE_NEW
        config.save()
        self.assertTrue(Subject.objects.count() ==
                        0 and SubjectSource.objects.count() == 0)
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source=self.test_source).count())
        self.assertTrue(SubjectSource.objects.count() ==
                        1 and Subject.objects.count() == 1)  # New subject created

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_new_device_handling_with_use_existing_config(self):
        subject_type = SubjectType.objects.create(value='Cats')
        subject_subtype = SubjectSubType.objects.create(
            value='queens', subject_type=subject_type)
        matching_subject = Subject.objects.create(
            name='Katie Kitten', subject_subtype=subject_subtype,
            additional={'sex': 'female'})
        SubjectSource.objects.create(
            subject=matching_subject, source=self.test_source)
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_name'] = 'Katie Kitten'
        obs_copy['manufacturer_id'] = 'new_source'

        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(len(Subject.objects.get(
            name='Katie Kitten').observations()), 0)

        self.assertEqual(1, SubjectSource.objects.filter(
            subject=matching_subject, source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # No new subject created
        self.assertEqual(Subject.objects.count(), 1)

        # Observation added to matching Subject
        self.assertEqual(len(Subject.objects.get(
            name='Katie Kitten').observations()), 1)

        # New source assignment added
        self.assertEqual(2, SubjectSource.objects.filter(
            subject=matching_subject).count())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_existing_config_match_case(self):
        subject_subtype = SubjectSubType.objects.get(value='rhino')
        matching_subject = Subject.objects.create(
            name='Fatu', subject_subtype=subject_subtype)
        SubjectSource.objects.create(
            subject=matching_subject, source=self.test_source)

        # Fatu still has no observations
        self.assertEqual(
            len(Subject.objects.get(name='Fatu').observations()), 0)
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_name'] = 'fatu'  # Note the lowercase
        obs_copy['manufacturer_id'] = 'new_source'

        self.assertEqual(1, SubjectSource.objects.filter(
            subject=matching_subject, source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # New observation added to matching Subject, Fatu/fatu considered a match
        self.assertEqual(
            len(Subject.objects.get(name='Fatu').observations()), 1)
        # No new subject created, Still only Fatu
        self.assertEqual(Subject.objects.count(), 1)

        self.config.new_device_match_case = True
        self.config.save()

        obs_copy['manufacturer_id'] = 'another_new_source'
        self.assertEqual(1, SubjectSource.objects.filter(
            subject=matching_subject, source=self.test_source).count())
        self._post_data(json.dumps(obs_copy), user=self.super_user)

        # New subject created and observation added to it, Fatu/fatu not considered a match
        self.assertEqual(Subject.objects.count(), 2)
        self.assertEqual(
            len(Subject.objects.get(name='fatu').observations()), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_use_existing_config_and_person_subtype_match(self):
        subject_type = SubjectType.objects.create(value='Cats')
        person_subject_type = SubjectType.objects.create(value='Person')
        subject_subtype = SubjectSubType.objects.create(
            value='queens', subject_type=subject_type)
        ranger_subject_subtype = SubjectSubType.objects.create(
            value='Ranger', subject_type=person_subject_type)

        subject_name = 'Katie Kitten'

        person_subject = Subject.objects.create(
            name=subject_name, subject_subtype=ranger_subject_subtype)  # Person Match

        other_subject = Subject.objects.create(
            name=subject_name, subject_subtype=subject_subtype)  # Other match

        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_name'] = 'Katie Kitten'
        obs_copy['manufacturer_id'] = 'new_source'

        self.assertEqual(Subject.objects.count(), 2)
        self.assertTrue(
            len(Subject.objects.get(name=subject_name, subject_subtype=ranger_subject_subtype).observations()) == 0 and
            len(Subject.objects.get(name=subject_name,
                                    subject_subtype=subject_subtype).observations()) == 0
        )

        self.assertEqual(0, SubjectSource.objects.filter(
            source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # No new subject created
        self.assertEqual(Subject.objects.count(), 2)

        # Observation added to matching Subject
        self.assertTrue(
            len(Subject.objects.get(name=subject_name, subject_subtype=ranger_subject_subtype).observations()) == 1 and
            len(Subject.objects.get(name=subject_name,
                                    subject_subtype=subject_subtype).observations()) == 0
        )

        # New source assignment added
        self.assertEqual(1, SubjectSource.objects.filter(
            subject=person_subject).count())
        self.assertEqual(0, SubjectSource.objects.filter(
            subject=other_subject).count())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_use_existing_config_and_other_subtype_matches(self):
        subject_type = SubjectType.objects.create(value='Cats')
        subject_subtype = SubjectSubType.objects.create(
            value='queens', subject_type=subject_type)

        wildlife_subject_type = SubjectType.objects.create(value='Wildlife')
        ranger_subject_subtype = SubjectSubType.objects.create(
            value='Rhinos', subject_type=wildlife_subject_type)

        subject_name = 'Katie Kitten'

        Subject.objects.create(
            name=subject_name, subject_subtype=ranger_subject_subtype)  # Other match 1
        Subject.objects.create(
            name=subject_name, subject_subtype=subject_subtype)  # Other match 2

        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_name'] = subject_name
        obs_copy['manufacturer_id'] = 'new_source'

        self.assertEqual(Subject.objects.count(), 2)
        self.assertTrue(
            len(Subject.objects.get(name=subject_name, subject_subtype=ranger_subject_subtype).observations()) == 0 and
            len(Subject.objects.get(name=subject_name,
                                    subject_subtype=subject_subtype).observations()) == 0
        )

        self.assertEqual(0, SubjectSource.objects.filter(
            source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # One more subject created, more than one other (Not person) match found
        self.assertEqual(Subject.objects.count(), 3)

        self.assertEqual(1, SubjectSource.objects.count())

        # Match on only one other subtype subjects
        subject_2_name = 'Katrina Kitten'
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy['subject_name'] = subject_2_name
        Subject.objects.create(
            name=subject_2_name, subject_subtype=subject_subtype)  # Other match 1

        self.assertEqual(Subject.objects.count(), 4)

        self._post_data(json.dumps(obs_copy), user=self.super_user)
        # No new subject created, only one other (than Person) match found
        self.assertEqual(Subject.objects.count(), 4)
        self.assertEqual(2, SubjectSource.objects.count())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_name_update_config(self):
        self.one_observation['subject_name'] = 'Fatu'
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source=self.test_source).count())

        subject = Subject.objects.first()
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(subject.name, 'Fatu')

        config = self.config
        config.name_change_config = UPDATE_NAME
        config.save()

        self.one_observation['subject_name'] = 'Najin'
        self.one_observation['recorded_at'] = "2019-04-10T12:01:00"
        # self.one_observation['subject_id'] = subject.id.hex

        response = self._post_data(json.dumps(
            self.one_observation), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Renamed subject
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(Subject.objects.first().name, 'Najin')

        # Observation added to given subject
        self.assertEqual(
            2, len(Subject.objects.get(name='Najin').observations()))
        self.assertEqual(2, Observation.objects.filter(
            source=self.test_source).count())

    def _generate_observations(self, n=10, distinct=False):
        for i in range(n):
            obs = dict(self.one_observation)
            if distinct:
                timestamp = pytz.utc.localize(
                    datetime.datetime.utcnow()) - datetime.timedelta(days=i)
                obs.update(recorded_at=timestamp.isoformat())

            yield obs

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def _post_data(self, payload, provider=None, user=None):
        if not provider:
            provider = self.provider

        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, user or self.app_user)
        response = ERTrackHandlerView.as_view()(request, provider_key=provider)
        return response

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
