import copy
import datetime
import json
from unittest import mock

from django.db import transaction
from django.test import override_settings
from django.urls import resolve
from rest_framework import status

from accounts.models import User
from core.tests import BaseAPITest, fake_get_pool
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)
from sensors.views import ERTrackHandlerView
from tracking.models.er_track import (
    CREATE_NEW,
    UPDATE_NAME,
    USE_EXISTING,
    SourceProviderConfiguration,
)


class ErTrackHandlerTest(BaseAPITest):
    source_type = "tracking-collar"
    sensor_type = "ertrack"
    provider = "test_provider"
    manufacturer_id = "ST2010-3034"

    one_observation = {
        "subject_name": "test_subject",
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2019-04-09T12:01:00Z",
        "location": {"lon": "31.19239", "lat": "-24.43071"},
    }

    second_observation = {
        "subject_name": "test_subject",
        "manufacturer_id": manufacturer_id,
        "recorded_at": "2019-04-09T12:02:00Z",
        "location": {"lon": "31.19239", "lat": "-24.43071"},
    }

    invalid_observation = {
        "event": "motionchange",
        "is_moving": False,
        "uuid": "280ebf2f-3c0e-4926-a080-65e8a140ea0f",
        "timestamp": "2024-01-02T11:06:56.048Z",
        "odometer": 319581.5,
        "coords": {
            "latitude": -0,
            "longitude": 0,
            "accuracy": 3.5,
            "speed": 0,
            "speed_accuracy": 1.7,
            "heading": -1,
            "heading_accuracy": -1,
            "altitude": 8.6,
            "altitude_accuracy": 12.5,
        },
        "activity": {"type": "still", "confidence": 100},
        "battery": {"is_charging": False, "level": 0.66},
        "extras": {},
    }

    def setUp(self):
        super().setUp()
        # setup db: create source, provider
        self.test_sourceprovider = SourceProvider.objects.create(display_name=self.provider, provider_key=self.provider)
        self.test_source = Source.objects.create(
            source_type=self.source_type, provider=self.test_sourceprovider, manufacturer_id=self.manufacturer_id
        )

        self.api_path = "/".join((self.api_base, "sensors", self.sensor_type, self.provider, "status"))
        self.super_user = User.objects.create_superuser(
            username="superuser", password="adfsfds32423", email="super@user.com"
        )
        self.config = SourceProviderConfiguration.objects.get(is_default=True)

    def test_url_handler(self):
        resolver = resolve(self.api_path + "/")
        assert resolver.func.cls == ERTrackHandlerView

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_observation_with_low_accuracy_is_excluded(self):
        obs = copy.deepcopy(self.one_observation)
        obs["additional"] = {"accuracy": 1000}
        response = self._post_data(json.dumps(obs), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        db_observation = Observation.objects.get(source=self.test_source, recorded_at=obs["recorded_at"])
        assert db_observation.exclusion_flags.EXCLUDED_AUTOMATICALLY.is_set

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_observation_with_high_accuracy_is_not_excluded(self):
        obs = copy.deepcopy(self.one_observation)
        obs["additional"] = {"accuracy": 1}
        response = self._post_data(json.dumps(obs), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        db_observation = Observation.objects.get(source=self.test_source, recorded_at=obs["recorded_at"])

        assert not any([f[1] for f in db_observation.exclusion_flags])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_observation_with_0_0_is_excluded(self):
        obs = copy.deepcopy(self.one_observation)
        obs["location"] = {"lon": 0, "lat": 0}
        obs["recorded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        response = self._post_data(json.dumps(obs), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        db_observation = Observation.objects.get(source=self.test_source, recorded_at=obs["recorded_at"])
        assert db_observation.exclusion_flags.EXCLUDED_AUTOMATICALLY.is_set

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_observation_with_1_1_is_excluded(self):
        obs = copy.deepcopy(self.one_observation)
        obs["location"] = {"lon": 1, "lat": 1}
        obs["recorded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        response = self._post_data(json.dumps(obs), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        db_observation = Observation.objects.get(source=self.test_source, recorded_at=obs["recorded_at"])
        assert db_observation.exclusion_flags.EXCLUDED_AUTOMATICALLY.is_set

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_a_duplicate_observation(self):
        response = self._post_data(json.dumps(self.one_observation), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self._post_data(json.dumps(self.one_observation), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_duplicate_in_a_batch_of_observations(self):
        response = self._post_data(
            json.dumps([self.one_observation, self.one_observation, self.one_observation]), user=self.super_user
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self._post_data(
            json.dumps([self.second_observation, self.one_observation, self.one_observation]), user=self.super_user
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_an_observation_with_invalid_observation(self):
        observations = [self.one_observation, self.invalid_observation]
        response = self._post_data(json.dumps(observations), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_one_invalid_observation(self):
        observations = [self.invalid_observation]
        response = self._post_data(json.dumps(observations), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_new_device_handling_with_create_new_config(self):
        config = self.config
        config.new_device_config = CREATE_NEW
        config.save()
        self.assertTrue(Subject.objects.count() == 0 and SubjectSource.objects.count() == 0)
        response = self._post_data(json.dumps(self.one_observation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=self.test_source).count())
        self.assertTrue(SubjectSource.objects.count() == 1 and Subject.objects.count() == 1)  # New subject created

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_new_device_handling_with_use_existing_config(self):
        subject_type = SubjectType.objects.create(value="Cats")
        subject_subtype = SubjectSubType.objects.create(value="queens", subject_type=subject_type)
        matching_subject = Subject.objects.create(
            name="Katie Kitten", subject_subtype=subject_subtype, additional={"sex": "female"}
        )
        SubjectSource.objects.create(subject=matching_subject, source=self.test_source)
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy["subject_name"] = "Katie Kitten"
        obs_copy["manufacturer_id"] = "new_source"

        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(len(Subject.objects.get(name="Katie Kitten").observations()), 0)

        self.assertEqual(1, SubjectSource.objects.filter(subject=matching_subject, source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # No new subject created
        self.assertEqual(Subject.objects.count(), 1)

        # Observation added to matching Subject
        self.assertEqual(len(Subject.objects.get(name="Katie Kitten").observations()), 1)

        # New source assignment added
        self.assertEqual(2, SubjectSource.objects.filter(subject=matching_subject).count())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_existing_config_match_case(self):
        subject_subtype = SubjectSubType.objects.get(value="rhino")
        matching_subject = Subject.objects.create(name="Fatu", subject_subtype=subject_subtype)
        SubjectSource.objects.create(subject=matching_subject, source=self.test_source)

        # Fatu still has no observations
        self.assertEqual(len(Subject.objects.get(name="Fatu").observations()), 0)
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy["subject_name"] = "fatu"  # Note the lowercase
        obs_copy["manufacturer_id"] = "new_source"

        self.assertEqual(1, SubjectSource.objects.filter(subject=matching_subject, source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # New observation added to matching Subject, Fatu/fatu considered a match
        self.assertEqual(len(Subject.objects.get(name="Fatu").observations()), 1)
        # No new subject created, Still only Fatu
        self.assertEqual(Subject.objects.count(), 1)

        self.config.new_device_match_case = True
        self.config.save()

        obs_copy["manufacturer_id"] = "another_new_source"
        self.assertEqual(1, SubjectSource.objects.filter(subject=matching_subject, source=self.test_source).count())
        self._post_data(json.dumps(obs_copy), user=self.super_user)

        # New subject created and observation added to it, Fatu/fatu not considered a match
        self.assertEqual(Subject.objects.count(), 2)
        self.assertEqual(len(Subject.objects.get(name="fatu").observations()), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_use_existing_config_and_person_subtype_match(self):
        subject_type = SubjectType.objects.create(value="Cats")
        person_subject_type = SubjectType.objects.create(value="Person")
        subject_subtype = SubjectSubType.objects.create(value="queens", subject_type=subject_type)
        ranger_subject_subtype = SubjectSubType.objects.create(value="Ranger", subject_type=person_subject_type)

        subject_name = "Katie Kitten"

        person_subject = Subject.objects.create(
            name=subject_name, subject_subtype=ranger_subject_subtype
        )  # Person Match

        other_subject = Subject.objects.create(name=subject_name, subject_subtype=subject_subtype)  # Other match

        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy["subject_name"] = "Katie Kitten"
        obs_copy["manufacturer_id"] = "new_source"

        self.assertEqual(Subject.objects.count(), 2)
        self.assertTrue(
            len(Subject.objects.get(name=subject_name, subject_subtype=ranger_subject_subtype).observations()) == 0
            and len(Subject.objects.get(name=subject_name, subject_subtype=subject_subtype).observations()) == 0
        )

        self.assertEqual(0, SubjectSource.objects.filter(source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # No new subject created
        self.assertEqual(Subject.objects.count(), 2)

        # Observation added to matching Subject
        self.assertTrue(
            len(Subject.objects.get(name=subject_name, subject_subtype=ranger_subject_subtype).observations()) == 1
            and len(Subject.objects.get(name=subject_name, subject_subtype=subject_subtype).observations()) == 0
        )

        # New source assignment added
        self.assertEqual(1, SubjectSource.objects.filter(subject=person_subject).count())
        self.assertEqual(0, SubjectSource.objects.filter(subject=other_subject).count())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_use_existing_config_and_other_subtype_matches(self):
        subject_type = SubjectType.objects.create(value="Cats")
        subject_subtype = SubjectSubType.objects.create(value="queens", subject_type=subject_type)

        wildlife_subject_type = SubjectType.objects.create(value="Wildlife")
        ranger_subject_subtype = SubjectSubType.objects.create(value="Rhinos", subject_type=wildlife_subject_type)

        subject_name = "Katie Kitten"

        Subject.objects.create(name=subject_name, subject_subtype=ranger_subject_subtype)  # Other match 1
        Subject.objects.create(name=subject_name, subject_subtype=subject_subtype)  # Other match 2

        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy["subject_name"] = subject_name
        obs_copy["manufacturer_id"] = "new_source"

        self.assertEqual(Subject.objects.count(), 2)
        self.assertTrue(
            len(Subject.objects.get(name=subject_name, subject_subtype=ranger_subject_subtype).observations()) == 0
            and len(Subject.objects.get(name=subject_name, subject_subtype=subject_subtype).observations()) == 0
        )

        self.assertEqual(0, SubjectSource.objects.filter(source=self.test_source).count())
        response = self._post_data(json.dumps(obs_copy), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # One more subject created, more than one other (Not person) match found
        self.assertEqual(Subject.objects.count(), 3)

        self.assertEqual(1, SubjectSource.objects.count())

        # Match on only one other subtype subjects
        subject_2_name = "Katrina Kitten"
        obs_copy = copy.deepcopy(self.one_observation)
        obs_copy["subject_name"] = subject_2_name
        Subject.objects.create(name=subject_2_name, subject_subtype=subject_subtype)  # Other match 1

        self.assertEqual(Subject.objects.count(), 4)

        self._post_data(json.dumps(obs_copy), user=self.super_user)
        # No new subject created, only one other (than Person) match found
        self.assertEqual(Subject.objects.count(), 4)
        self.assertEqual(2, SubjectSource.objects.count())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_name_existing_config_without_permission(self):
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["subject_name"] = "Fatu"
        response = self._post_data(json.dumps(obs_one))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=self.test_source).count())

        subject = Subject.objects.first()
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(subject.name, "Fatu")

        config = self.config
        config.name_change_config = USE_EXISTING
        config.save()

        obs_one["recorded_at"] = "2019-04-10T12:01:00"

        response = self._post_data(json.dumps(obs_one))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_name_change_config_without_permission(self):
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["subject_name"] = "Fatu"
        response = self._post_data(json.dumps(obs_one))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=self.test_source).count())

        subject = Subject.objects.first()
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(subject.name, "Fatu")

        config = self.config
        config.name_change_config = UPDATE_NAME
        config.save()

        obs_one["subject_name"] = "Najin"
        obs_one["recorded_at"] = "2019-04-10T12:01:00"

        response = self._post_data(json.dumps(obs_one))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_device_handling_with_name_update_config(self):
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["subject_name"] = "Fatu"
        response = self._post_data(json.dumps(obs_one))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source=self.test_source).count())

        subject = Subject.objects.first()
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(subject.name, "Fatu")

        config = self.config
        config.name_change_config = UPDATE_NAME
        config.save()

        obs_one["subject_name"] = "Najin"
        obs_one["recorded_at"] = "2019-04-10T12:01:00"

        response = self._post_data(json.dumps(obs_one), user=self.super_user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Renamed subject
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(Subject.objects.first().name, "Najin")

        # Observation added to given subject
        self.assertEqual(2, len(Subject.objects.get(name="Najin").observations()))
        self.assertEqual(2, Observation.objects.filter(source=self.test_source).count())

    def _generate_observations(self, n=10, distinct=False):
        for i in range(n):
            obs = dict(self.one_observation)
            if distinct:
                timestamp = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=i)
                obs.update(recorded_at=timestamp.isoformat())

            yield obs

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_subject_by_name_assigned_to_different_user_with_permission(self):
        # setup by creating user linked subject attached to our source
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["user_id"] = str(self.app_user.id)
        obs_one["subject_name"] = "Empty"
        response = self._post_data(json.dumps(obs_one), user=self.app_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=self.app_user.get_full_name()).count() == 1

        # allow setting a different source for a subject by name linked to another user
        obs_two = copy.deepcopy(self.second_observation)
        obs_two["subject_name"] = self.app_user.get_full_name()
        obs_two["manufacturer_id"] = "ER Mobile 1"
        response = self._post_data(json.dumps(obs_two), user=self.super_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=obs_two["subject_name"]).count() == 2

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_subject_by_name_assigned_to_different_user_without_permission(self):
        # setup by creating user linked subject attached to our source
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["user_id"] = str(self.super_user.id)
        obs_one["subject_name"] = "Super User"
        response = self._post_data(json.dumps(obs_one), user=self.super_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=self.super_user.get_full_name()).count() == 1

        # allow setting a different source for a subject by name linked to another user
        obs_two = copy.deepcopy(self.second_observation)
        obs_two["subject_name"] = self.super_user.get_full_name()
        obs_two["manufacturer_id"] = "ER Mobile 1"
        response = self._post_data(json.dumps(obs_two), user=self.app_user)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=obs_two["subject_name"]).count() == 1

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_subject_by_id_linked_to_this_user(self):
        # setup by creating user linked subject attached to our source
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["user_id"] = str(self.app_user.id)
        obs_one["subject_name"] = "App User"
        response = self._post_data(json.dumps(obs_one), user=self.app_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1

        obs_two = copy.deepcopy(self.second_observation)
        obs_two["message_key"] = "create-source-subject"
        obs_two["manufacturer_id"] = obs_one["manufacturer_id"]
        obs_two["subject_id"] = str(Subject.objects.by_linked_user_id(user_id=self.app_user.id).id)

        response = self._post_data(json.dumps(obs_two), user=self.app_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=self.app_user.get_full_name()).count() == 1

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_subject_by_id_assigned_to_different_user_by_user_with_permission(self):
        # setup by creating user linked subject attached to our source
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["user_id"] = str(self.app_user.id)
        obs_one["subject_name"] = "App User"
        response = self._post_data(json.dumps(obs_one), user=self.app_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1

        # allow setting a different source for a subject by id linked to another user
        obs_two = copy.deepcopy(self.second_observation)
        obs_two["manufacturer_id"] = "ER Mobile 1"
        obs_two["subject_id"] = str(Subject.objects.by_linked_user_id(user_id=self.app_user.id).id)
        response = self._post_data(json.dumps(obs_two), user=self.super_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=self.app_user.get_full_name()).count() == 2

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_subject_by_id_assigned_to_different_user_by_user_without_permission(self):
        # setup by creating user linked subject attached to our source
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["user_id"] = str(self.super_user.id)
        obs_one["subject_name"] = "Super User"
        response = self._post_data(json.dumps(obs_one), user=self.super_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1

        # allow setting a different source for a subject by id linked to another user
        obs_two = copy.deepcopy(self.second_observation)
        obs_two["manufacturer_id"] = "ER Mobile 1"
        obs_two["subject_id"] = str(Subject.objects.by_linked_user_id(user_id=self.super_user.id).id)
        response = self._post_data(json.dumps(obs_two), user=self.app_user)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Subject.objects.count() == 1
        assert SubjectSource.objects.filter(subject__name=self.super_user.get_full_name()).count() == 1

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_post_change_subject_attached_to_source_with_use_existing_config(self):
        # setup by creating user linked subject attached to our source
        obs_one = copy.deepcopy(self.one_observation)
        obs_one["user_id"] = str(self.super_user.id)
        obs_one["subject_name"] = "Super User"
        response = self._post_data(json.dumps(obs_one), user=self.super_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 1

        # setup second user linked subject attatched to another source
        obs_two = copy.deepcopy(self.one_observation)
        obs_two["manufacturer_id"] = "ER Mobile 1"
        obs_two["user_id"] = str(self.app_user.id)
        response = self._post_data(json.dumps(obs_two), user=self.app_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 2
        assert SubjectSource.objects.filter(subject__name=self.app_user.get_full_name()).count() == 1

        # ER Mobile wants to set the TrackedBy to an existing subject
        # assign obs_two subject to obs_one source
        obs_three = copy.deepcopy(self.second_observation)
        obs_three["subject_name"] = self.app_user.get_full_name()
        response = self._post_data(json.dumps(obs_three), user=self.super_user)
        assert response.status_code == status.HTTP_201_CREATED
        assert Subject.objects.count() == 2
        assert SubjectSource.objects.filter(subject__name=obs_three["subject_name"]).count() == 2
        assert SubjectSource.objects.filter(source__manufacturer_id=obs_one["manufacturer_id"]).count() == 2

    def test_apply_exclusion_flags_manual_exclusion(self):
        """Test that manual exclusion flags from observation data are applied correctly."""
        from sensors.handlers import ErTrackHandler

        observation_dict = {
            "location": {"latitude": 1.0, "longitude": 1.0},
            "recorded_at": "2023-01-01T00:00:00Z",
            "source": "test_source",
            "additional": {},
        }
        an_observation = {
            "exclusion_flags": 1,
            "location": {"lat": 1.0, "lon": 1.0},
            "recorded_at": "2023-01-01T00:00:00Z",
        }

        result = ErTrackHandler.apply_exclusion_flags(observation_dict, an_observation)

        assert result.get("exclusion_flags") == 1
        assert result["location"] == {"latitude": 1.0, "longitude": 1.0}

    def test_apply_exclusion_flags_automatic_exclusion_high_accuracy(self):
        """Test that automatic exclusion flags are applied for high accuracy values."""
        from observations.models import Observation
        from sensors.handlers import ErTrackHandler

        observation_dict = {
            "location": {"latitude": 1.0, "longitude": 1.0},
            "recorded_at": "2023-01-01T00:00:00Z",
            "source": "test_source",
            "additional": {},
        }
        an_observation = {"location": {"lat": 1.0, "lon": 1.0}, "recorded_at": "2023-01-01T00:00:00Z"}
        location = {"latitude": 1.0, "longitude": 1.0}
        additional = {"accuracy": 1000}  # High accuracy value

        result = ErTrackHandler.apply_exclusion_flags(observation_dict, an_observation, location, additional)

        assert result.get("exclusion_flags") == Observation.EXCLUDED_AUTOMATICALLY

    def test_apply_exclusion_flags_automatic_exclusion_invalid_coords(self):
        """Test that automatic exclusion flags are applied for invalid coordinates (0,0)."""
        from observations.models import Observation
        from sensors.handlers import ErTrackHandler

        observation_dict = {
            "location": {"latitude": 0.0, "longitude": 0.0},
            "recorded_at": "2023-01-01T00:00:00Z",
            "source": "test_source",
            "additional": {},
        }
        an_observation = {"location": {"lat": 0.0, "lon": 0.0}, "recorded_at": "2023-01-01T00:00:00Z"}
        location = {"latitude": 0.0, "longitude": 0.0}
        additional = {"accuracy": 0}

        result = ErTrackHandler.apply_exclusion_flags(observation_dict, an_observation, location, additional)

        assert result.get("exclusion_flags") == Observation.EXCLUDED_AUTOMATICALLY

    def test_apply_exclusion_flags_automatic_exclusion_1_1_coords(self):
        """Test that automatic exclusion flags are applied for coordinates (1,1)."""
        from observations.models import Observation
        from sensors.handlers import ErTrackHandler

        observation_dict = {
            "location": {"latitude": 1.0, "longitude": 1.0},
            "recorded_at": "2023-01-01T00:00:00Z",
            "source": "test_source",
            "additional": {},
        }
        an_observation = {"location": {"lat": 1.0, "lon": 1.0}, "recorded_at": "2023-01-01T00:00:00Z"}
        location = {"latitude": 1.0, "longitude": 1.0}
        additional = {"accuracy": 0}

        result = ErTrackHandler.apply_exclusion_flags(observation_dict, an_observation, location, additional)

        assert result.get("exclusion_flags") == Observation.EXCLUDED_AUTOMATICALLY

    def test_should_exclude_automatically_high_accuracy(self):
        """Test that should_exclude_automatically returns True for high accuracy values."""
        from sensors.handlers import ErTrackHandler

        location = {"latitude": 1.0, "longitude": 1.0}
        additional = {"accuracy": 1000}  # High accuracy value

        result = ErTrackHandler.should_exclude_automatically(location, additional)

        assert result is True

    def test_should_notexclude_automatically_low_accuracy(self):
        """Test that should_exclude_automatically returns False for low accuracy values."""
        from sensors.handlers import ErTrackHandler

        location = {"latitude": -1.2921, "longitude": 36.8219}  # Nairobi, Kenya coordinates
        additional = {"accuracy": 1}  # Low accuracy value

        result = ErTrackHandler.should_exclude_automatically(location=location, additional=additional)

        assert result is False

    def test_should_exclude_automatically_invalid_coords(self):
        """Test that should_exclude_automatically returns True for invalid coordinates."""
        from sensors.handlers import ErTrackHandler

        # Test (0,0) coordinates
        location = {"latitude": 0.0, "longitude": 0.0}
        additional = {"accuracy": 0}

        result = ErTrackHandler.should_exclude_automatically(location=location, additional=additional)
        assert result is True

        # Test (1,1) coordinates
        location = {"latitude": 1.0, "longitude": 1.0}
        additional = {"accuracy": 0}

        result = ErTrackHandler.should_exclude_automatically(location=location, additional=additional)
        assert result is True

    def test_should_not_exclude_automatically_missing_accuracy(self):
        """Test that should_exclude_automatically handles missing accuracy field."""
        from sensors.handlers import ErTrackHandler

        location = {"latitude": -1.2921, "longitude": 36.8219}  # Nairobi, Kenya coordinates
        additional = {}  # No accuracy field

        result = ErTrackHandler.should_exclude_automatically(location=location, additional=additional)

        assert result is False

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def _post_data(self, payload, provider=None, user=None):
        if not provider:
            provider = self.provider

        request = self.factory.post(self.api_path, data=payload, content_type="application/json")
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
            with mock.patch(
                "django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block", lambda a: False
            ):
                transaction.get_connection(using=db_name).run_and_clear_commit_hooks()

    def tearDown(self):
        self.run_transaction_hooks()
