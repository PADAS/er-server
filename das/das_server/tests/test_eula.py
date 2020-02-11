from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from core.tests import BaseAPITest
from das_server import views
from das_server.models import EULA


class EulaModelTestCase(TestCase):
    def setUp(self) -> None:
        self.user1 = User.objects.create_user(
            username='user1',
            password='asdfo9823sfiu23$',
            email='user1user@user.org')
        self.user2 = User.objects.create_user(
            username='user2',
            password='asdfo9823sfiu23$',
            email='user2user@user.org')
        self.user3 = User.objects.create_user(
            username='user3',
            password='asdfo9823sfiu23$',
            email='user3user@user.org')

    def test_only_unique_eula_version_numbers_accepted(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version_number=2.0)

        with self.assertRaises(IntegrityError):
            EULA.objects.create(eula_url="http://some.com/eula.pdf",
                                version_number=2.0,)

    def test_only_one_active_eula_can_exist_at_any_time(self):
        EULA.objects.create(eula_url="http://some.com/eula1.0.pdf",
                            version_number=2.0,
                            active=True)
        EULA.objects.create(eula_url="http://some.com/eula1.1.pdf",
                            version_number=2.1,
                            active=True)
        latest_eula = EULA.objects.create(
            eula_url="http://some.com/eula1.3.pdf", version_number=2.2,
            active=True)

        self.assertEqual(len(EULA.objects.filter(active=True)), 1)
        active_eula = EULA.objects.get(active=True)
        self.assertEqual(active_eula, latest_eula)

    def test_get_current_eula_version(self):
        EULA.objects.create(eula_url="http://some.com/eula1.0.pdf",
                            version_number=2.0,
                            active=True)
        eula = EULA.objects.create(eula_url="http://some.com/eula1.4.pdf",
                                   version_number=2.4)
        active_eula = EULA.objects.get_active_eula()
        self.assertEqual(active_eula, eula)

    def test_get_users_that_agreed_to_current_eula_version(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version_number=2.0,
                            active=True)
        EULA.objects.accept_eula(user=self.user1)
        self.assertEqual(
            EULA.objects.get_users_that_have_accepted_the_latest_eula().count(),
            1)

    def test_get_users_that_have_acknowledged_eula(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version_number=2.0,
                            active=True)
        EULA.objects.accept_eula(user=self.user1)
        self.assertEqual(
            EULA.objects.get_users_that_have_not_accepted_latest_eula().count(),
            User.objects.count() - 1)


class EulaViewsTestCase(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()
        self.api_base = '/api/v1.0'
        self.user = User.objects.create_user(
            'user', 'das_user@vulcan.com', 'user',
            **self.user_const)

    def test_getting_active_eula(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version_number=2.0,
                            active=True)
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version_number=2.1)

        request = self.factory.get(self.api_base + '/eula/')
        self.force_authenticate(request, self.user)

        response = views.GetActiveEulaAPIView.as_view()(request)
        data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(eula.eula_url, data.get("eula_url"))
        self.assertEqual(eula.version_number,
                         float(data.get("version_number", 0.0)))

    def test_accept_eula_view(self):
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version_number=2.1)
        data = {"eula": eula.id, "user": self.user.id}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user)
        response = views.AcceptEulaAPIView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(id=self.user.id)
        self.assertTrue(user.accepted_eula)
        self.assertTrue(response_data.get('accepted'))
        self.assertEqual(response_data.get('eula'), eula.id)
