from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.test import TestCase, override_settings

from accounts import views
from accounts.models import User
from accounts.models.eula import EULA, UserAgreement
from core.tests import BaseAPITest


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
                            version="EarthRanger_EULA_ver2025-02-12")

        with self.assertRaises(IntegrityError):
            EULA.objects.create(eula_url="http://some.com/eula.pdf",
                                version="EarthRanger_EULA_ver2025-02-12",)

    def test_only_one_active_eula_can_exist_at_any_time(self):
        EULA.objects.create(eula_url="http://some.com/eula1.0.pdf",
                            version="EarthRanger_EULA_ver2025-02-12",
                            active=True)
        EULA.objects.create(eula_url="http://some.com/eula1.1.pdf",
                            version="EarthRanger_EULA_ver2025-03-12",
                            active=True)
        latest_eula = EULA.objects.create(
            eula_url="http://some.com/eula1.3.pdf",
            version="EarthRanger_EULA_ver2025-04-12",
            active=True)

        self.assertEqual(len(EULA.objects.filter(active=True)), 1)
        active_eula = EULA.objects.get(active=True)
        self.assertEqual(active_eula, latest_eula)

    def test_get_current_eula_version(self):
        EULA.objects.create(eula_url="http://some.com/eula1.0.pdf",
                            version="EarthRanger_EULA_ver2025-02-12",
                            active=True)
        eula = EULA.objects.create(eula_url="http://some.com/eula1.4.pdf",
                                   version="EarthRanger_EULA_ver2025-06-12")
        active_eula = EULA.objects.get_active_eula()
        self.assertEqual(active_eula, eula)

    def test_get_users_that_agreed_to_current_eula_version(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version="EarthRanger_EULA_ver2025-02-12",
                            active=True)
        EULA.objects.accept_eula(user=self.user1)
        self.assertEqual(
            EULA.objects.get_users_that_have_accepted_the_latest_eula().count(),
            1)

    def test_get_users_that_have_acknowledged_eula(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version="EarthRanger_EULA_ver2025-02-12",
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
        self.user2 = User.objects.create_user(
            username='user2',
            password='asdfo9823sfiu23$',
            email='user2user@user.org')

    @override_settings(ACCEPT_EULA=True)
    def test_getting_active_eula(self):
        EULA.objects.create(eula_url="http://some.com/eula.pdf",
                            version="EarthRanger_EULA_ver2025-02-12",
                            active=True)
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version="EarthRanger_EULA_ver2025-03-12")

        request = self.factory.get(self.api_base + '/eula/')
        self.force_authenticate(request, self.user)

        response = views.GetActiveEulaAPIView.as_view()(request)
        data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(eula.eula_url, data.get("eula_url"))
        self.assertEqual(eula.version,
                         data.get("version", "0.0"))
        self.assertEqual(str(eula.id), data.get("id"))

    @override_settings(ACCEPT_EULA=True)
    def test_accept_eula_view(self):
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version="EarthRanger_EULA_ver2025-03-12")
        data = {"eula": eula.id, "user": self.user.id}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user)
        response = views.AcceptEulaAPIView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(id=self.user.id)
        self.assertTrue(user.accepted_eula)
        self.assertTrue(response_data.get('accept'))
        self.assertEqual(response_data.get('eula'), eula.id)

    @override_settings(ACCEPT_EULA=True)
    def test_revoke_eula_acceptance_view(self):
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version="EarthRanger_EULA_ver2025-03-12")
        data = {"eula": eula.id, "user": self.user.id, "accept": True}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user)
        response = views.AcceptEulaAPIView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(id=self.user.id)
        self.assertTrue(user.accepted_eula)
        self.assertTrue(response_data.get('accept'))
        self.assertEqual(response_data.get('eula'), eula.id)

        agreement_id = response_data.get('id')

        data = {"eula": eula.id, "user": self.user.id, "accept": False}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user)
        response = views.AcceptEulaAPIView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(id=self.user.id)
        self.assertFalse(user.accepted_eula)
        with self.assertRaises(ObjectDoesNotExist):
            UserAgreement.objects.get(id=agreement_id)

        data = {"eula": eula.id, "user": self.user.id, "accept": True}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user)
        response = views.AcceptEulaAPIView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(id=self.user.id)
        self.assertTrue(user.accepted_eula)

    @override_settings(ACCEPT_EULA=False)
    def test_get_eula_returns_200_for_sites_that_dont_accept_eula(self):
        request = self.factory.get(self.api_base + '/eula/')
        self.force_authenticate(request, self.user)

        response = views.GetActiveEulaAPIView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("version", response.data)

    @override_settings(ACCEPT_EULA=False)
    def test_accepted_eula_not_returned_for_sites_not_using_eula(self):
        request = self.factory.get(self.api_base + '/user/me')
        self.force_authenticate(request, self.user)

        response = views.UserView.as_view()(request,
                                            id=self.user.id)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('accepted_eula', response_data)

    @override_settings(ACCEPT_EULA=True)
    def test_user_cannot_accept_eula_for_another_user(self):
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version="EarthRanger_EULA_ver2025-03-12")
        data = {"eula": eula.id, "user": self.user.id}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user2)
        response = views.AcceptEulaAPIView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    @override_settings(ACCEPT_EULA=True)
    def test_sending_same_data_twice_returns_200_ok(self):
        eula = EULA.objects.create(eula_url="http://some.com/eulav1.1.pdf",
                                   version="EarthRanger_EULA_ver2025-03-12")
        data = {"eula": eula.id, "user": self.user.id}
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, self.user)
        response = views.AcceptEulaAPIView.as_view()(request)
        first_response_data = response.data
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(id=self.user.id)
        self.assertTrue(user.accepted_eula)
        self.assertTrue(first_response_data.get('accept'))
        self.assertEqual(first_response_data.get('eula'), eula.id)

        # 2nd time
        request = self.factory.post(self.api_base + '/eula/accept/', data)
        self.force_authenticate(request, user)
        response = views.AcceptEulaAPIView.as_view()(request)
        second_response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(first_response_data.get("eula")), str(second_response_data.get("eula")))
        self.assertEqual(str(first_response_data.get("user")), str(second_response_data.get("user")))
        user = User.objects.get(id=self.user.id)
        self.assertTrue(user.accepted_eula)






