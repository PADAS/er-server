import os
import django.contrib.auth
from django.core.management import call_command
from django.urls import reverse
from core.tests import BaseAPITest
from activity.models import PatrolType
from activity.views import PatrolTypesView, PatrolTypeView

User = django.contrib.auth.get_user_model()
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')


class TestPatrolType(BaseAPITest):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'test_patroltype')

        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)

    def test_get_all_patroltypes(self):
        patrol_types = PatrolType.objects.all()
        url = reverse('patrol-types')

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = PatrolTypesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), len(patrol_types))

    def test_get_one_patroltype_by_id(self):
        dog_patrol_id = 'c84bc72f-96d6-4248-9fea-7dd0bbc8c190'
        url = reverse('patrol-type', kwargs={'id': dog_patrol_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = PatrolTypeView.as_view()(request, id=dog_patrol_id)
        self.assertEqual(response.status_code, 200)
