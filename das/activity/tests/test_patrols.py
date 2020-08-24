import os
import django.contrib.auth
from django.core.management import call_command
from django.urls import reverse
from core.tests import BaseAPITest
from activity.models import PatrolType, Patrol
from activity import views
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

    def test_create_patrol(self):
        patrol_data = dict(
            serial_number=3, title='Test Patrol', objective='Test Objective',
            time_range={"lower": "2020-08-04 04:00:00+03", "upper": "2020-11-04 04:00:00+03"})
        request = self.factory.post(self.api_base + '/patrols/', patrol_data)
        self.force_authenticate(request, self.app_user)

        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 201

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
