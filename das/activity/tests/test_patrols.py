import datetime
import json
import os
from urllib.parse import urlencode

import django.contrib.auth
from django.core.management import call_command
from django.urls import reverse

from activity import views
from activity.models import Patrol, PatrolSegment, PatrolType
from core.tests import BaseAPITest

User = django.contrib.auth.get_user_model()
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')


class TestPatrol(BaseAPITest):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'test_patroltype')

        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)
        Patrol.objects.bulk_create(
            [
                Patrol(id="b14bc72f-96d6-4248-9fea-7dd0bbc8c196", serial_number=1, title='Test Patrol', objective='Test Objective'),
                Patrol(serial_number=2, title='Test Patrol 2', objective='Test Objective 2')
            ])
        PatrolSegment.objects.create(patrol_type=PatrolType.objects.first())

    def test_get_all_patroltypes(self):
        patrol_types = PatrolType.objects.all()
        url = reverse('patrol-types')

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolTypesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), len(patrol_types))

    def test_get_one_patroltype_by_id(self):
        dog_patrol_id = 'c84bc72f-96d6-4248-9fea-7dd0bbc8c190'
        url = reverse('patrol-type', kwargs={'id': dog_patrol_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolTypeView.as_view()(request, id=dog_patrol_id)
        self.assertEqual(response.status_code, 200)

    def test_get_all_patrols(self):
        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200
        assert len(response.data) == 2

    def test_get_one_patrol_by_id(self):
        patrol_id = 'b14bc72f-96d6-4248-9fea-7dd0bbc8c196'
        url = reverse('patrol', kwargs={'id': patrol_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolView.as_view()(request, id=patrol_id)
        assert response.status_code == 200

    def test_create_patrolsegment(self):
        patrolsgm_data = dict(scheduled_start='2020-08-05 02:00:00+00',
                              time_range={"lower": "2020-08-05 02:00:00+00", "upper": "2020-08-06 04:00:00+00"},
                              start_location={'latitude': '-122.334', 'longitude': '47.598'},
                              end_location={'latitude': '-124.54', 'longitude': '38.98'},
                              state='active'
                              )
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrolsgm_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_get_all_patrolsegments(self):
        url = reverse('patrol-segments')
        request = self.factory.get(url)
        patrolsgm = PatrolSegment.objects.all().count()
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), patrolsgm)

    def test_get_one_patrolsegment_by_id(self):
        patrolsgm = PatrolSegment.objects.first()
        patrolsgm_id = str(patrolsgm.id)
        url = reverse('patrol-segment', kwargs={'id': patrolsgm_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsegmentView.as_view()(request, id=patrolsgm_id)
        self.assertEqual(response.status_code, 200)

    def test_patrol_filter(self):
        patrol_data = dict(
            title='Test Patrol',
            objective='Test Objective',
            time_range={"lower": "2020-08-01 02:00:00+00", "upper": "2020-08-02 04:00:00+00"}
        )
        self._create_patrol(patrol_data)
        query = {'filter': json.dumps({"date_range": {"lower": "2020-08-01T00:00:00.000Z"}})}
        url = reverse('patrols')
        url += f'?{urlencode(query)}'
        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0].get('title'), patrol_data.get('title'))

    def _create_patrol(self, patrol_data):
        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
