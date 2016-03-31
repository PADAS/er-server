import datetime

import pytz
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth.models import Permission
from oauth2_provider.models import Application, AccessToken
from django.contrib.gis.geos import Point
from django.utils import timezone

from accounts.models import User, PermissionSet
from observations.models import Subject, SubjectGroup, Source, SubjectSource, Observation
import observations.views as views

API_BASE = '/api/v1.0'

class BasePermissionTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user('super', 'super@test.com', 'super', is_superuser=True, is_staff=True)
        self.last_view_user = User.objects.create_user('last_view_joe', 'last_joe@test.com', 'last_view_joe')
        self.realtime_view_user = User.objects.create_user('realtime_joe', 'realtimejoe@test.com', 'realtime_view_joe')
        self.delayed_view_user = User.objects.create_user('delayed_view_joe', 'jerry@test.com', 'delayed_view_joe')
        self.no_view_user = User.objects.create_user('no_view_john', 'john@test.com', 'no_view_john')

        self.application = Application(
        name="Test Application",
        redirect_uris="http://localhost",
        user=self.last_view_user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )
        self.application.save()


        self.subject_set = PermissionSet.objects.create(name='subject')
        self.subject_view_last_set = PermissionSet.objects.create(name='subject_view')
        self.subject_view_delayed_set = PermissionSet.objects.create(name='subject_view_delayed')
        self.subject_view_realtime_set = PermissionSet.objects.create(name='subject_view_realtime')

        self.view_subject_name = 'view_subject'
        self.view_subject = Permission.objects.get(codename=self.view_subject_name)

        self.view_last_position_name = 'view_last_position'
        self.view_last_position = Permission.objects.get(codename=self.view_last_position_name)

        self.view_real_time_name = 'view_real_time'
        self.view_real_time = Permission.objects.get(codename=self.view_real_time_name)

        self.view_delayed_name = 'view_delayed'
        self.view_delayed = Permission.objects.get(codename=self.view_delayed_name)

        self.subject_view_last_set.parent = self.subject_set
        self.subject_view_last_set.permissions.add(self.view_last_position)
        self.subject_view_last_set.permissions.add(self.view_subject)
        self.subject_view_last_set.save()

        self.subject_view_realtime_set.parent = self.subject_set
        self.subject_view_realtime_set.permissions.add(self.view_real_time)
        self.subject_view_realtime_set.permissions.add(self.view_subject)
        self.subject_view_realtime_set.save()

        self.subject_view_delayed_set.parent = self.subject_set
        self.subject_view_delayed_set.permissions.add(self.view_delayed)
        self.subject_view_delayed_set.permissions.add(self.view_subject)
        self.subject_view_delayed_set.save()

        self.all_group = SubjectGroup.objects.create(name='all_group')

        self.ele = Subject.objects.create(name="ele", additional={})
        self.ele_group = SubjectGroup.objects.create(name='ele_group',
                                                     parent=self.all_group)
        self.ele.group = self.ele_group
        self.ele.save()

        self.ranger = Subject.objects.create(name="ranger", additional={})
        self.ranger_group = SubjectGroup.objects.create(name='ranger_group',
                                                        parent=self.all_group)
        self.ranger.group = self.ranger_group
        self.ranger.save()



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

        self.ele_group.permission_sets.add(self.subject_view_last_set)
        self.ele_group.permission_sets.add(self.subject_view_delayed_set)
        self.ele_group.permission_sets.add(self.subject_view_realtime_set)
        self.ele_group.save()

        self.last_view_user.permission_sets.add(self.subject_view_last_set)
        self.last_view_user.save()

        self.delayed_view_user.permission_sets.add(self.subject_view_delayed_set)
        self.delayed_view_user.save()

        self.realtime_view_user.permission_sets.add(self.subject_view_realtime_set)
        self.realtime_view_user.save()


class SubjectViewPermissionsTest(BasePermissionTest):
    def setUp(self):
        super(SubjectViewPermissionsTest, self).setUp()
        self.factory = APIRequestFactory(enforce_csrf_checks=True)

    def force_authenticate(self, request, user):
        request.user = user
        tok = AccessToken.objects.create(
            user=request.user, token='1234567890',
            application=self.application, scope='read write',
            expires=timezone.now() + datetime.timedelta(days=1)
        )

        force_authenticate(request, user=request.user, token=tok)

    def test_return_current_observation_for_subject(self):
        request = self.factory.get(API_BASE + '/subject/')
        self.force_authenticate(request, self.last_view_user)

        response = views.SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue('last_position_date' in response.data)
        self.assertEqual(self.ob_today.recorded_at, response.data['last_position_date'])

    def test_not_return_current_observation_for_subject(self):
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

    def test_return_all_observation_for_subject(self):
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
