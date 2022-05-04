from datetime import datetime, timedelta

import pytest
import pytz

from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.test import TestCase

from accounts.models import PermissionSet, User
from observations.models import (Observation, Subject, SubjectGroup,
                                 SubjectMaximumSpeed)


def make_perm(perm):
    return "{0}.{1}".format(perm.content_type.app_label, perm.codename)


class SubjectGroupTestCase(TestCase):
    def setUp(self):
        all_set = PermissionSet.objects.create(name='all')
        some_set = PermissionSet.objects.create(name='some')

        some_set.parent = all_set
        some_set.save()

    def test_subject_in_group(self):
        ele = Subject.objects.create_subject(name='ele', additional={})
        ele_group = SubjectGroup.objects.create(name='ele_group')

        ele.groups.add(ele_group)

        ele = Subject.objects.get(name='ele')
        self.assertIn(ele_group, ele.groups.all())


class SubjectPermissionsTestCase(TestCase):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')
        self.view_last_position_name = 'view_last_position'

        self.view_last_position = Permission.objects.get(
            codename=self.view_last_position_name)

        self.some_set.parent = self.all_set
        self.some_set.permissions.add(
            Permission.objects.get(codename=self.view_last_position_name))
        self.some_set.save()

        self.superuser = User.objects.create_superuser('admin',
                                                       'admin@test.com',
                                                       'admin',
                                                       **self.user_const)
        self.user = User.objects.create_user('joe', 'joe@example.com', 'joe',
                                             **self.user_const)

    def test_user_has_view_permission(self):
        user = User.objects.create_user(username='active_user',
                                        email='active_user@test.com',
                                        password=User.objects.make_random_password(),
                                        **self.user_const)

        user.permission_sets.add(self.some_set)

        ele = Subject.objects.create_subject(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name='ele_group')
        ele.groups.add(ele_group)

        ele_group.permission_sets.add(self.some_set)

        self.assertTrue(user.has_perm(make_perm(self.view_last_position), ele))

        # view_perm = Permission.objects.get()


class SubjectAlertTestCase(TestCase):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')

        self.some_set.parent = self.all_set
        self.some_set.save()

    def test_return_user(self):
        user = User.objects.create_user(username='active_user',
                                        email='active_user@test.com',
                                        password=User.objects.make_random_password(),
                                        **self.user_const)
        user.permission_sets.add(self.some_set)
        user.permission_sets.add(self.all_set)
        user.save()

        user2 = User.objects.create_user(username='no_alert',
                                         email='active@test.com',
                                         password=User.objects.make_random_password(),
                                         **self.user_const)

        ele = Subject.objects.create_subject(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name='ele_group')
        ele.groups.add(ele_group)

        ele_group.permission_sets.add(self.some_set)

        self.assertIn(user, ele.get_users_to_notify())
        self.assertNotIn(user2, ele.get_users_to_notify())

    def test_permission_with_proxy_content_type_created(self):
        """
        A proxy model's permissions use its own content type rather than the
        content type of the concrete model.
        """
        opts = SubjectMaximumSpeed._meta
        codename = get_permission_codename('add', opts)
        self.assertTrue(
            Permission.objects.filter(
                content_type__model=opts.model_name,
                content_type__app_label=opts.app_label,
                codename=codename,
            ).exists())


@pytest.mark.django_db
class TestObservationManager:
    OBSERVATION_POINTS = [
        (-103.64398956298828, 20.612540918310213),
        (0, 0),
        (-103.57738494873045, 20.70313296563719),
        (0, 0),
        (-103.50425720214844, 20.639531429485633),
    ]
    EMPTY_OBSERVATION_POINTS = [(0, 0), (0, 0), (0, 0), (0, 0), (0, 0)]

    @pytest.mark.parametrize("include_empty_location", [False, True])
    def test_get_last_source_observation_with_bunch_of_observations(
        self, subject_source, include_empty_location
    ):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        latest_observation_id = None
        for count, point in enumerate(self.OBSERVATION_POINTS, 1):
            observation = Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(point),
                source=source,
            )
            if count == 1:
                latest_observation_id = observation.id

        observation = Observation.objects.get_last_source_observation(
            source, include_empty_location=include_empty_location
        )

        assert latest_observation_id == observation.id

    def test_get_last_source_observation_with_all_empty_observations_include_empty_observations(
        self, subject_source
    ):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        latest_observation_id = None
        for count, point in enumerate(self.EMPTY_OBSERVATION_POINTS, 1):
            observation = Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(point),
                source=source,
            )
            if count == 1:
                latest_observation_id = observation.id

        observation = Observation.objects.get_last_source_observation(
            source, include_empty_location=True
        )

        assert latest_observation_id == observation.id

    def test_get_last_source_observation_with_all_empty_observations_not_include_empty_observations(
        self, subject_source
    ):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        for count, point in enumerate(self.EMPTY_OBSERVATION_POINTS, 1):
            Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(point),
                source=source,
            )

        observation = Observation.objects.get_last_source_observation(
            source, include_empty_location=False
        )

        assert observation is None
