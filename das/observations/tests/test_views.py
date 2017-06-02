import datetime

import pytz
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth.models import Permission
from oauth2_provider.models import Application, AccessToken
from django.contrib.gis.geos import Point
from django.utils import timezone

from core.tests import BaseAPITest
from accounts.models import User, PermissionSet
from observations.models import Subject, SubjectGroup, Source, SubjectSource, Observation
import observations.views as views

API_BASE = '/api/v1.0'

class BasePermissionTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.superuser = User.objects.create_user('super', 'super@test.com', 'super', is_superuser=True, is_staff=True, **user_const)
        self.realtime_view_user = User.objects.create_user('realtime_joe', 'realtimejoe@test.com', 'realtime_view_joe', **user_const)
        self.delayed_view_user = User.objects.create_user('delayed_view_joe', 'jerry@test.com', 'delayed_view_joe', **user_const)
        self.no_view_user = User.objects.create_user('no_view_john', 'john@test.com', 'no_view_john', **user_const)
        self.source_admin_user = User.objects.create_user('john_the_source_admin', 'john.source@test.com', 'john_the_source_admin', **user_const)

        self.source_set = PermissionSet.objects.create(name='source')
        self.source_set.permissions.add(Permission.objects.get_by_natural_key(
            'view_sourcegroup', 'observations', 'sourcegroup'))
        self.source_admin_user.permission_sets.add(self.source_set)


        self.subject_set = PermissionSet.objects.create(name='subject')
        self.subject_view_last_set = PermissionSet.objects.create(name='subject_view')
        self.subject_view_delayed_set = PermissionSet.objects.create(name='subject_view_delayed')
        self.subject_view_realtime_set = PermissionSet.objects.create(name='subject_view_realtime')

        self.view_subjectgroup = Permission.objects.get_by_natural_key(
            'view_subjectgroup', 'observations', 'subjectgroup')

        self.view_subject_name = 'view_subject'
        self.view_subject = Permission.objects.get(codename=self.view_subject_name)

        self.view_begins_permission_name = 'access_begins_60'
        self.view_begins_permission = Permission.objects.get(codename=self.view_begins_permission_name)

        self.view_last_position_name = 'access_ends_0'
        self.view_last_position = Permission.objects.get(codename=self.view_last_position_name)

        self.view_real_time_name = 'access_ends_0'
        self.view_real_time = Permission.objects.get(codename=self.view_real_time_name)

        self.view_delayed_name = 'access_ends_1'
        self.view_delayed = Permission.objects.get(codename=self.view_delayed_name)

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
        datetime.datetime(3030, 1, 1, tzinfo=pytz.utc)
        )
        source = Source.objects.create(additional={})
        subject_source = SubjectSource.objects.create(assigned_range=DEFAULT_DATE_RANGE,
                                                      source=source,
                                                      subject=self.ele,
                                                      additional={})
        t = datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(hours=26)
        self.ob_yesterday =  Observation.objects.create(
                source_id=source.id,
                location=Point((31,0)),
                recorded_at=t,
                additional={}
            )

        t = datetime.datetime.now(tz=pytz.UTC)
        self.ob_today =  Observation.objects.create(
                source_id=source.id,
                location=Point((31,0)),
                recorded_at=t,
                additional={}
            )

        self.ele_group.permission_sets.add(self.subject_view_realtime_set)
        self.ele_group.save()

        self.all_group.permission_sets.add(self.subject_view_realtime_set)
        self.all_group.save()

        self.ele_group.permission_sets.add(self.subject_view_delayed_set)
        self.ele_group.save()

        self.delayed_view_user.permission_sets.add(self.subject_view_delayed_set)
        self.delayed_view_user.save()

        self.realtime_view_user.permission_sets.add(self.subject_view_realtime_set)
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
        self.assertNotEqual(self.ob_today.recorded_at, response.data['last_position_date'])

    def test_not_return_subject_sources(self):
        request = self.factory.get(API_BASE + '/subject/{0}/sources'.format(self.ele.id))
        self.force_authenticate(request, self.no_view_user)

        response = views.SubjectSourcesView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 403)

    def xtest_return_all_observation_for_subject(self):
        request = self.factory.get(API_BASE + '/subject/')
        self.force_authenticate(request, self.realtime_view_user)

        response = views.SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue('last_position_date' in response.data)
        self.assertEqual(self.ob_today.recorded_at, response.data['last_position_date'])
        self.assertEqual(self.ob_yesterday.recorded_at, response.data['tracks_range'][0])

    def test_user_return_subject_sources(self):
        request = self.factory.get(API_BASE + '/subject/{0}/sources'.format(self.ele.id))
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectSourcesView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)

    def test_return_subjects_bbox_no_view(self):
        bbox = '37.18,0.1,37.55,0.54'
        request = self.factory.get(API_BASE + '/subjects/')
        self.force_authenticate(request, self.no_view_user)

        response = views.SubjectsView.as_view()(request, bbox=bbox)
        self.assertEqual(response.status_code, 403)

    def test_return_subjects_bbox_view_delayed(self):
        bbox = '37.18,0.1,37.55,0.54'
        request = self.factory.get(API_BASE + '/subjects/?bbox={0}'.format(bbox))
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_not_return_ranger_in_subjects_call(self):
        request = self.factory.get(API_BASE + '/subjects/')
        self.force_authenticate(request, self.delayed_view_user)

        response = views.SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse([s for s in response.data if s['id'] == str(self.ranger.id) ])


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


class SourceGroupViewTest(BasePermissionTest):
    def setUp(self):
        super().setUp()

    def test_user_return_source_groups(self):
        request = self.factory.get(
            API_BASE + '/sourcegroups')
        self.force_authenticate(request, self.source_admin_user)

        response = views.SourceGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
