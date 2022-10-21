import datetime
import random
from datetime import timedelta
from typing import NamedTuple
from urllib.parse import urlencode

import dateutil.parser
import pytest
import pytz

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.test import override_settings
from django.urls import resolve, reverse

from accounts.models import PermissionSet, User
from client_http import HTTPClient
from core.tests import API_BASE, BaseAPITest
from observations import views
from observations.models import (DEFAULT_ASSIGNED_RANGE, Observation, Source,
                                 SourceGroup, Subject, SubjectGroup,
                                 SubjectSource)
from observations.views import SourceSubjectsView, SourceView


def random_string(length=10):
    return ''.join(random.choice('abcdefghijklmnopqrstuvwxyz01234567890$@') for _ in range(length))


class BasePermissionTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.superuser = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True, is_staff=True, **user_const)
        self.realtime_view_user = User.objects.create_user(
            'realtime_joe', 'realtimejoe@test.com', 'realtime_view_joe', **user_const)
        self.delayed_view_user = User.objects.create_user(
            'delayed_view_joe', 'jerry@test.com', 'delayed_view_joe', **user_const)
        self.no_view_user = User.objects.create_user(
            'no_view_john', 'john@test.com', 'no_view_john', **user_const)
        self.source_admin_user = User.objects.create_user(
            'john_the_source_admin', 'john.source@test.com', 'john_the_source_admin', **user_const)

        self.source_set = PermissionSet.objects.create(name='source')
        self.source_set.permissions.add(Permission.objects.get_by_natural_key(
            'view_sourcegroup', 'observations', 'sourcegroup'))
        self.source_admin_user.permission_sets.add(self.source_set)

        self.subject_set = PermissionSet.objects.create(name='subject')
        self.subject_view_last_set = PermissionSet.objects.create(
            name='subject_view')
        self.subject_view_delayed_set = PermissionSet.objects.create(
            name='subject_view_delayed')
        self.subject_view_realtime_set = PermissionSet.objects.create(
            name='subject_view_realtime')

        self.view_subjectgroup = Permission.objects.get_by_natural_key(
            'view_subjectgroup', 'observations', 'subjectgroup')

        self.view_subject_name = 'view_subject'
        self.view_subject = Permission.objects.get(
            codename=self.view_subject_name)

        self.view_begins_permission_name = 'access_begins_60'
        self.view_begins_permission = Permission.objects.get(
            codename=self.view_begins_permission_name)

        self.view_last_position_name = 'access_ends_0'
        self.view_last_position = Permission.objects.get(
            codename=self.view_last_position_name)

        self.view_real_time_name = 'access_ends_0'
        self.view_real_time = Permission.objects.get(
            codename=self.view_real_time_name)

        self.view_delayed_name = 'access_ends_1'
        self.view_delayed = Permission.objects.get(
            codename=self.view_delayed_name)

        self.subject_set.children.add(self.subject_view_last_set)
        self.subject_view_last_set.permissions.add(
            self.view_last_position, self.view_subject, self.view_subjectgroup)
        self.subject_view_last_set.permissions.add(
            self.view_begins_permission, self.view_subject, self.view_subjectgroup)

        self.subject_set.children.add(self.subject_view_realtime_set)
        self.subject_view_realtime_set.permissions.add(
            self.view_real_time, self.view_subject, self.view_subjectgroup)
        self.subject_view_realtime_set.permissions.add(
            self.view_begins_permission, self.view_subject, self.view_subjectgroup)

        self.subject_set.children.add(self.subject_view_delayed_set)
        self.subject_view_delayed_set.permissions.add(
            self.view_delayed, self.view_subject, self.view_subjectgroup)
        self.subject_view_delayed_set.permissions.add(
            self.view_begins_permission, self.view_subject, self.view_subjectgroup)

        self.all_group = SubjectGroup.objects.create(name='all_group')

        self.ele = Subject.objects.create(name="ele", additional={})
        self.ele_group = SubjectGroup.objects.create(name='ele_group')
        self.all_group.children.add(self.ele_group)

        self.ele.groups.add(self.ele_group)

        self.ranger = Subject.objects.create(name="ranger", additional={})
        self.ranger_group = SubjectGroup.objects.create(name='ranger_group')
        self.all_group.children.add(self.ranger_group)

        self.ranger.groups.add(self.ranger_group)

        DEFAULT_DATE_RANGE = (
            datetime.datetime(2015, 11, 1, tzinfo=pytz.utc),
            dateutil.parser.parse("9999-12-31 23:59:59+0000")
        )

        source = Source.objects.create(additional={})
        subject_source = SubjectSource.objects.create(assigned_range=DEFAULT_DATE_RANGE,
                                                      source=source,
                                                      subject=self.ele,
                                                      additional={})
        t = datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(hours=26)
        self.ob_yesterday = Observation.objects.create(
            source_id=source.id,
            location=Point((31, 0)),
            recorded_at=t,
            additional={}
        )

        t = datetime.datetime.now(tz=pytz.UTC)
        self.ob_today = Observation.objects.create(
            source_id=source.id,
            location=Point((31, 0)),
            recorded_at=t,
            additional={}
        )

        self.ele_group.permission_sets.add(self.subject_view_realtime_set)
        self.ele_group.save()

        self.all_group.permission_sets.add(self.subject_view_realtime_set)
        self.all_group.save()

        self.ele_group.permission_sets.add(self.subject_view_delayed_set)
        self.ele_group.save()

        self.delayed_view_user.permission_sets.add(
            self.subject_view_delayed_set)
        self.delayed_view_user.save()

        self.realtime_view_user.permission_sets.add(
            self.subject_view_realtime_set)
        self.realtime_view_user.save()


class SubjectViewPermissionsTest(BasePermissionTest):
    def setUp(self):
        super().setUp()

    def xtest_not_return_current_observation_for_subject(self):
        request = self.factory.get(API_BASE + '/subject/')
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue('last_position_date' in response.data)
        self.assertNotEqual(self.ob_today.recorded_at,
                            response.data['last_position_date'])

    def test_not_return_subject_sources(self):
        request = self.factory.get(
            API_BASE + '/subject/{0}/sources'.format(self.ele.id))
        self.force_authenticate(request, self.no_view_user)

        response = views.SubjectSourcesView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 403)

    @override_settings(TIME_ZONE="Africa/Nairobi")
    def test_return_subject_sources(self):
        request = self.factory.get(
            API_BASE + '/subject/{0}/subjectsources'.format(self.ele.id))
        self.force_authenticate(request, self.realtime_view_user)

        response = views.SubjectSubjectSourcesView.as_view()(request, id=str(self.ele.id))
        assert response.status_code == 200
        assert len(response.data)

    def test_return_all_observation_for_subject(self):
        request = self.factory.get(API_BASE + '/subject/')
        self.force_authenticate(request, self.realtime_view_user)

        response = views.SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue('last_position_date' in response.data)
        self.assertEqual(self.ob_today.recorded_at,
                         response.data['last_position_date'])

    def test_unauthorised_observation_viewing_of_subject(self):
        request = self.factory.get(API_BASE + '/subject/')
        self.force_authenticate(request, self.no_view_user)
        response = views.SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'], [])

    def test_user_return_subject_sources(self):
        request = self.factory.get(
            API_BASE + '/subject/{0}/sources'.format(self.ele.id))
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectSourcesView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)

    def test_return_subjects_bbox_no_view(self):
        bbox = '37.18,0.1,37.55,0.54'
        request = self.factory.get(API_BASE + '/subjects/')
        self.force_authenticate(request, self.no_view_user)

        response = views.SubjectsView.as_view()(request, bbox=bbox)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'], [])

    def test_return_subjects_bbox_view_delayed(self):
        bbox = '37.18,0.1,37.55,0.54'
        request = self.factory.get(
            API_BASE + '/subjects/?bbox={0}'.format(bbox))
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_not_return_ranger_in_subjects_call(self):
        request = self.factory.get(API_BASE + '/subjects/')
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            [s for s in response.data if s['id'] == str(self.ranger.id)])

    def authenticate_user_and_get_subjects(self, url):
        request = self.factory.get(API_BASE + url)
        self.force_authenticate(request, self.superuser)
        return views.SubjectsView.as_view()(request)

    def test_subjects_api_call_only_returns_active_subjects(self):
        response = self.authenticate_user_and_get_subjects('/subjects/')
        self.assertEqual(response.status_code, 200)

        # Returns all 2 subjects: Both are active
        self.assertEqual(len(response.data), 2)

        # Update one subject, set to inactive
        self.ele.is_active = False
        self.ele.save()
        response = self.authenticate_user_and_get_subjects('/subjects/')

        # Only one subject is returned, only one is active
        self.assertEqual(len(response.data), 1)

        # adding `include_inactive=True` param fetches both active and inactive
        response = self.authenticate_user_and_get_subjects(
            '/subjects/?include_inactive=True')
        self.assertEqual(len(response.data), 2)

    def test_subjectsview_having_perms_via_sourcegroup(self):

        expected_subject_name = 'ele no. 2'
        # Fixtures for testing subject access via source-group.
        user_with_sourcegroup_access = User.objects.create_user(
            username='ele2owner', email='ele2owner@test.com', password=random_string(10), last_name='Bar', first_name='Foo')
        ele2 = Subject.objects.create(
            name=expected_subject_name, additional={})
        ele2_source = Source.objects.create(manufacturer_id='ele2-source')
        ele2_subjectsource = SubjectSource.objects.create(source=ele2_source, subject=ele2,
                                                          assigned_range=(datetime.datetime(1000, 1, 1, tzinfo=pytz.utc),
                                                                          datetime.datetime(9999, 1, 1, tzinfo=pytz.utc)))
        ele2_sourcegroup = SourceGroup.objects.create(name='ele2 source group')
        ele2_sourcegroup.sources.add(ele2_source)

        # Give permissions by source group permission set.
        view_ele2_sourcegroup_ps = PermissionSet.objects.create(
            name='View Ele2 Source Group')

        perms = Permission.objects.get_by_natural_key(
            'view_sourcegroup', 'observations', 'sourcegroup')
        view_ele2_sourcegroup_ps.permissions.add(perms)
        ele2_sourcegroup.permission_sets.add(view_ele2_sourcegroup_ps)

        user_with_sourcegroup_access.permission_sets.add(
            view_ele2_sourcegroup_ps)

        p1 = PermissionSet.objects.create(
            name='sourcegroup user subject view perms')
        perms = Permission.objects.get_by_natural_key(
            'view_subject', 'observations', 'subject')
        p1.permissions.add(perms)
        user_with_sourcegroup_access.permission_sets.add(p1)

        # Two assertions on test fixtures.
        self.assertEqual(ele2_sourcegroup.permission_sets.all().count(), 1)
        self.assertEqual(SourceGroup.objects.filter(
            permission_sets__in=user_with_sourcegroup_access.get_all_permission_sets()).count(), 1)

        # Make the request
        request = self.factory.get(API_BASE + '/subjects/')
        self.force_authenticate(request, user_with_sourcegroup_access)

        response = views.SubjectsView.as_view()(request,)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], expected_subject_name)


class SubjectGroupViewTest(BasePermissionTest):
    def setUp(self):
        super().setUp()

    def test_delay_view_user_return_subject_groups(self):
        request = self.factory.get(
            API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'ele_group')

    def test_realtime_view_user_return_subject_groups(self):
        request = self.factory.get(
            API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.realtime_view_user)

        response = views.SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'all_group')

    def test_superuser_return_subject_groups(self):
        return_groups = ('Subjects', 'all_group')
        request = self.factory.get(
            API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.superuser)

        response = views.SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertTrue(response.data[0]['name'] in return_groups)
        self.assertTrue(response.data[1]['name'] in return_groups)

    def test_return_single_subject_group_by_id(self):
        request = self.factory.get(
            API_BASE + '/subjectgroup/{id}'.format(id=self.ele_group.id))
        self.force_authenticate(request, self.superuser)

        response = views.SubjectGroupView.as_view()(request,
                                                    id=str(self.ele_group.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.ele_group.id))

    def test_not_return_subject_group_no_view_permission(self):
        request = self.factory.get(
            API_BASE + '/subjectgroup/{id}'.format(id=self.ele_group.id))
        self.force_authenticate(request, self.no_view_user)

        response = views.SubjectGroupView.as_view()(request,
                                                    id=str(self.ele_group.id))
        self.assertEqual(response.status_code, 403)

    def test_not_return_subject_groups_no_view_permission(self):
        request = self.factory.get(
            API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.no_view_user)

        response = views.SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'], [])


class SourceGroupViewTest(BasePermissionTest):
    def setUp(self):
        super().setUp()

    def test_user_return_source_groups(self):
        request = self.factory.get(
            API_BASE + '/sourcegroups')
        self.force_authenticate(request, self.source_admin_user)

        response = views.SourceGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_user_return_source_groups_no_view_permission(self):
        request = self.factory.get(
            API_BASE + '/sourcegroups')
        self.force_authenticate(request, self.no_view_user)

        response = views.SourceGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 403)


class ObservationViewTestCase(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')

        self.user = User.objects.create_user(
            'user', 'das_user@vulcan.com', 'user', is_superuser=True, is_staff=True, **self.user_const)
        self.elephant = Subject.objects.create_subject(
            id='d2ed403e-9419-41aa-8fa9-45a70e5ce2ef', name='Elephant 1',
            subject_subtype_id='elephant')

        source_args = {
            'subject': {'name': str(self.elephant.id)},
            'provider': 'test_provider',
            'manufacturer_id': 'best_manufacturer'
        }
        self.collar = Source.objects.ensure_source(**source_args)

        self.fixed_latitude = float(random.randint(3000, 3000)) / 100
        self.fixed_longitude = float(random.randint(2800, 4000)) / 100

        location = Point(x=self.fixed_longitude, y=self.fixed_latitude)
        self.additional = {"Name": "Name"}
        self.observation_time = pytz.UTC.localize(datetime.datetime.now())
        self.observation_data = {
            'recorded_at': self.observation_time,
            'location': location,
            'source': self.collar,
            'additional': self.additional
        }

        self.observation_post_data = {
            "location": {
                "latitude": self.fixed_latitude,
                "longitude": self.fixed_longitude
            },
            "recorded_at": "2020-11-19T04:26:02.968Z",
            "additional": {},
            "source": str(self.collar.id)
        }

        self.observation = Observation.objects.create(**self.observation_data)

        DEFAULT_DATE_RANGE = (
            datetime.datetime(2015, 11, 1, tzinfo=pytz.utc),
            dateutil.parser.parse("9999-12-31 23:59:59+0000")
        )
        SubjectSource.objects.create(
            assigned_range=DEFAULT_DATE_RANGE,
            source=self.collar,
            subject=self.elephant,
            additional={})

        self.ele_group = SubjectGroup.objects.create(name='ele_group')
        self.elephant.groups.add(self.ele_group)

        self.observations_readonly_user = User.objects.create_user(
            'observations_readonly_user', None, 'observations_readonly_user', is_superuser=False, is_staff=False, **user_const)

        self.observations_readwrite_user = User.objects.create_user(
            'observations_readwrite_user', 'readwrite@test.com', 'observations_readwrite_user', is_superuser=False, is_staff=False, **user_const)

        self.observation_view_set = PermissionSet.objects.create(
            name='observation_view_set')
        self.observation_view_set.permissions.add(
            Permission.objects.get(codename='view_observation'))
        self.observations_readonly_user.permission_sets.add(
            self.observation_view_set)

        self.observation_readwrite_set = PermissionSet.objects.create(
            name='observation_readwrite_set')
        self.observation_readwrite_set.permissions.add(
            Permission.objects.get(codename='add_observation'))
        self.observation_readwrite_set.permissions.add(
            Permission.objects.get(codename='view_observation'))
        self.observations_readwrite_user.permission_sets.add(
            self.observation_readwrite_set)

        self.ele_group.permission_sets.add(self.observation_readwrite_set)

    def test_return_observations_by_subjectsource(self):
        subjectsource_id = str(self.elephant.subjectsources.all()[0].id)

        url = reverse('observations-list-view')
        url += '?{}'.format(urlencode({'subjectsource_id': subjectsource_id}))

        request = self.factory.get(self.api_base + url)

        self.force_authenticate(request, self.user)

        response = views.ObservationsView.as_view()(request)
        assert response.status_code == 200
        assert len(response.data)

    def test_include_details_false(self):
        url = reverse('observations-list-view')
        url += '?{}'.format(urlencode({'include_details': 'false'}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = views.ObservationsView.as_view()(request)
        results = response.data.get('results', [])
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(results), 1)

        obs = results[0]
        self.assertNotIn('observation_addtional', obs.keys())

    def test_include_details_true(self):
        url = reverse('observations-list-view')
        url += '?{}'.format(urlencode({'include_details': 'true'}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = views.ObservationsView.as_view()(request)
        results = response.data.get('results', [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(results), 1)

        obs = results[0]
        self.assertIn('observation_details', obs.keys())
        self.assertEqual(obs.get('observation_details'), self.additional)

    def test_include_details_not_specified(self):
        url = reverse('observations-list-view')

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = views.ObservationsView.as_view()(request)
        results = response.data.get('results', [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(results), 1)

        obs = results[0]
        self.assertNotIn('observation_details', obs.keys())

    def test_filter_observations_by_subject_id(self):
        filter_params = {'subject_id': self.elephant.id}
        response = self.make_observations_filter_request(filter_params)

        # all records are of the given subject
        self.assertTrue(self.elephant.observations().count(),
                        response.data.get('count'))

    def test_filter_observations_by_source_id(self):
        filter_params = {'source_id': self.collar.id}
        response = self.make_observations_filter_request(filter_params)

        # all records are of the given source
        self.assertTrue(
            all(k.get('source') == self.collar.id for k in response.data.get('results')))

    def test_filter_observations_by_recorded_since(self):
        filter_params = {'since': self.observation_time + timedelta(days=1)}
        response = self.make_observations_filter_request(filter_params)

        # no records 1 days from last observations creation date
        self.assertEquals(response.data.get('count'), 0)

    def test_filter_observations_by_recorded_until(self):
        filter_params = {'until': self.observation_time + timedelta(days=1)}
        response = self.make_observations_filter_request(filter_params)

        self.assertEquals(response.data.get('count'), 1)

    def test_filter_observations_by_date_range(self):
        self.observation_data['recorded_at'] = self.observation_time + \
            timedelta(days=4)
        self.observation2 = Observation.objects.create(**self.observation_data)

        filter_params = {
            'since': self.observation_time,
            'until': self.observation_time + timedelta(days=5)}
        response = self.make_observations_filter_request(filter_params)

        # self.observation and self.observation both lie in this range
        self.assertEquals(response.data.get('count'), 2)

    def make_observations_filter_request(self, filter_params):
        url = reverse('observations-list-view')
        url += f'?{urlencode(filter_params)}'
        request = self.factory.get(self.api_base + url)

        self.force_authenticate(request, self.user)
        response = views.ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response

    def test_observation_readonly_can_view(self):
        url = reverse('observations-list-view')

        request = self.factory.get(
            self.api_base + url)
        self.force_authenticate(request, self.observations_readonly_user)

        response = views.ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_observation_readonly_cannot_add(self):
        url = reverse('observations-list-view')

        request = self.factory.post(
            self.api_base + url, self.observation_post_data)
        self.force_authenticate(request, self.observations_readonly_user)

        response = views.ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_observation_can_add(self):
        url = reverse('observations-list-view')

        request = self.factory.post(
            self.api_base + url, self.observation_post_data)
        self.force_authenticate(request, self.observations_readwrite_user)

        response = views.ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 201)


@pytest.fixture
def user_with_one_week_track_perms(db, django_user_model):
    user_const = dict(last_name='last', first_name='first')
    user = User.objects.create_user('perms_user',
                                    'das_perms@vulcan.com',
                                    'perms',
                                    **user_const)

    subject_set = PermissionSet.objects.create(name='subject_perm_set')
    permission_names = [
        "Can view subject",
        "Can view tracks no more than 7 days old",
        "Can view tracks no less than 0 days old",
        "Can view tracks no less than 1 day old",
        "Can view tracks no less than 3 days old",
        "Can view tracks no less than 7 days old",
    ]
    for name in permission_names:
        subject_set.permissions.add(Permission.objects.get(name=name))
    user.permission_sets.add(subject_set)
    return user


class UserSubject(NamedTuple):
    user: any
    subject: Subject


@pytest.fixture
def subject_with_month_long_track(db, user_with_one_week_track_perms):
    subject = Subject.objects.create_subject(
        name="Bobo", subject_subtype_id='elephant')
    source = Source.objects.create(manufacturer_id='random-collar')
    subjectgroup = SubjectGroup.objects.create(name="Bobo_subjectgroup")
    subjectgroup.subjects.add(subject)
    subjectgroup.permission_sets.set(
        user_with_one_week_track_perms.permission_sets.all())
    SubjectSource.objects.create(
        subject=subject, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    next_time = now - datetime.timedelta(days=31)
    x = 37.5
    y = 0.56
    while now > next_time:
        x += (random.random() - 0.5) / 10000
        y += (random.random() - 0.5) / 10000
        Observation.objects.create(
            source=subject.source,
            location=Point(x=x, y=y),
            recorded_at=next_time,
            additional={}
        )
        next_time += datetime.timedelta(hours=6)

    return UserSubject(user_with_one_week_track_perms, subject)


def test_one_week_track_permissions(subject_with_month_long_track, client):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    oldest_time = now - datetime.timedelta(days=31)

    user, subject = (subject_with_month_long_track.user,
                     subject_with_month_long_track.subject)
    client.force_login(user)
    url = reverse("subject-view-tracks", kwargs=dict(subject_id=subject.id))
    response = client.get(url + "?since=" + oldest_time.isoformat())
    max_day = datetime.datetime.combine(datetime.date.today(
    ) - datetime.timedelta(days=7), datetime.time.min, tzinfo=datetime.timezone.utc)
    assert response.status_code == 200
    assert not [t for t in response.data['features'][0]
                ['properties']['coordinateProperties']['times'] if t < max_day]

    # 'Can view all historical tracks' perm will precede over 'Can view tracks no more than 7 days old' perm.
    SubjectGroup.objects.create(name="Kittens")
    kitten_ps = PermissionSet.objects.get(name='View Kittens Subject Group')
    kitten_ps.permissions.add(Permission.objects.get(
        name='Can view all historical tracks'))
    user.permission_sets.add(kitten_ps)

    url = reverse("subject-view-tracks", kwargs=dict(subject_id=subject.id))
    response = client.get(url + "?since=" + oldest_time.isoformat())
    max_day = datetime.datetime.combine(datetime.date.today(
    ) - datetime.timedelta(days=7), datetime.time.min, tzinfo=datetime.timezone.utc)
    assert response.status_code == 200
    assert [t for t in response.data['features'][0]['properties']
            ['coordinateProperties']['times'] if t > max_day]


@pytest.mark.django_db
class TestSourceProvider:
    def test_update_source_provider_with_patch_method(self, source_provider):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        request = client.factory.patch(
            f"{client.api_base}/sourceprovider/{source_provider.id}/",
            data={
                "provider_key": "New provider key",
                "display_name": "This is a provider key",
                "additional": {},
            },
        )
        client.force_authenticate(request, client.app_user)
        response = views.SourceProvidersViewPartial.as_view()(
            request, id=source_provider.id
        )

        assert response.status_code == 200
        assert response.data.get("provider_key") == "New provider key"
        assert response.data.get("display_name") == "This is a provider key"
        assert response.data.get("additional") == {}

    def test_update_source_provider_with_put_method(self, source_provider):
        client = HTTPClient()
        client.app_user.is_superuser = True
        request = client.factory.put(
            f"{client.api_base}/sourceprovider/{source_provider.id}/",
            data={
                "provider_key": "New provider key",
                "display_name": "This is a provider key",
                "additional": {},
            },
        )
        client.force_authenticate(request, client.app_user)
        response = views.SourceProvidersViewPartial.as_view()(
            request, id=source_provider.id
        )

        assert response.status_code == 200
        assert response.data.get("provider_key") == "New provider key"
        assert response.data.get("display_name") == "This is a provider key"
        assert response.data.get("additional") == {}


@pytest.mark.django_db
class TestSourceSubjectsView:

    def test_create_subject_source(self, subject_source):
        subject = subject_source.subject
        source = subject_source.source
        url = f"{reverse('source-subjects-view', kwargs={'id': source.id})}"
        client = HTTPClient()
        data = {
            "assigned_range": {
                "lower": "2022-05-01T17:00:00-07:00",
                "upper": "2022-05-05T16:59:59-07:00"
            },
            "source": source.id,
            "subject": subject.id,
            "additional": {},
            "location": {
                "latitude": 20.420935,
                "longitude": -103.313486
            }
        }
        subject_source_count = SubjectSource.objects.all().count()

        request = client.factory.post(url, data=data)
        client.force_authenticate(request, client.app_user)
        response = SourceSubjectsView.as_view()(request, id=str(subject.id))

        assert response.status_code == 201
        assert SubjectSource.objects.all().count() == subject_source_count + 1


@pytest.mark.django_db
class TestSourceView:

    def test_resolve_url(self):
        resolver = resolve("/api/v1.0/source/manufacturer/")

        assert resolver.func.cls == SourceView
