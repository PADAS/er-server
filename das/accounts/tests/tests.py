import copy

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.utils import lorem_ipsum
from rest_framework.test import APIClient

from accounts.models import PermissionSet, User
import accounts.views as views
from core.tests import BaseAPITest


class BaseTestCase(TestCase):
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')

        self.all_set.children.add(self.some_set)


class PermissionSetTestCase(BaseTestCase):
    def test_some_is_member_of_all(self):
        all_set = PermissionSet.objects.get(name='all')
        some_set = PermissionSet.objects.get(name='some')

        self.assertIn(some_set, all_set.children.all())
        self.assertIn(all_set.id, some_set.get_ancestor_ids())


class UserModelTest(TestCase):
    password = User.objects.make_random_password()
    user_const = dict(last_name='last', first_name='first')

    def test_caseinsensitive_name(self):

        user = User.objects.create(username='user',
                                   password=self.password,
                                   email='user@test.com',
                                   **self.user_const)

        with self.assertRaises(ValidationError):
            user2 = User.objects.create(username='User',
                                        email='user2@test.com',
                                        password=self.password,
                                        **self.user_const)

    def test_get_by_username(self):
        user = User.objects.create(username='User',
                                   email='user3@test.com',
                                   password=self.password,
                                   **self.user_const)

        user2 = User.objects.get(username='user')
        self.assertEqual(user.pk, user2.pk)
        user2 = User.objects.get(username='User')
        self.assertEqual(user.pk, user2.pk)

    def test_get_kml_key(self):
        user = User.objects.create(username='User',
                                   email='user4@test.com',
                                   password=self.password,
                                   **self.user_const)
        token = user.get_kml_access_token()
        print(token)


class TestAuthentication(BaseAPITest):
    password = User.objects.make_random_password()
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()

        nologin_const = copy.copy(self.user_const)
        nologin_const['is_nologin'] = True
        self.nologin_user = User.objects.create_user('nologin_user',
                                                     'das_nologin_user@vulcan.com', self.password, **nologin_const)

        self.joc_supervisor = User.objects.create_user(
            'joc_supervisor', 'das_joc_supervisor@vulcan.com', self.password,
            **self.user_const)
        self.joc_supervisor.act_as_profiles.add(self.nologin_user)

        staff_const = copy.copy(self.user_const)
        staff_const['is_staff'] = True
        self.staff_user = User.objects.create_user(
            'staff_user', 'das_staff_user@vulcan.com', self.password,
            **staff_const)

        self.super_user = User.objects.create_superuser(
            'super_user', 'das_super_user@vulcan.com', self.password,
            **self.user_const)

    def not_allow_nologin_user(self):
        client = APIClient()
        request = self.factory.get(self.api_base + '/user/me')
        self.force_authenticate(request, self.nologin_user)

        response = views.UserView.as_view()(request,
                                            id='me')
        self.assertEqual(response.status_code, 403)

    def act_as_nologin_user(self):
        request = self.factory.get(self.api_base + '/user/me')
        request.META['HTTP_USER_PROFILE'] = str(self.nologin_user.pk)
        self.force_authenticate(request, self.joc_supervisor)

        response = views.UserView.as_view()(request,
                                            id='me')
        self.assertEqual(response.status_code, 200)
        data = response

    def fail_act_as_superuser(self):
        request = self.factory.get(self.api_base + '/user/me')
        request.META['HTTP_USER_PROFILE'] = str(self.super_user.pk)
        self.force_authenticate(request, self.joc_supervisor)

        response = views.UserView.as_view()(request,
                                            id='me')
        self.assertEqual(response.status_code, 403)

    def fail_act_as_unlisted_user(self):
        request = self.factory.get(self.api_base + '/user/me')
        request.META['HTTP_USER_PROFILE'] = str(self.staff_user)
        self.force_authenticate(request, self.joc_supervisor)

        response = views.UserView.as_view()(request,
                                            id='me')
        self.assertEqual(response.status_code, 403)
