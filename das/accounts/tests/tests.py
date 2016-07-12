from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.utils import lorem_ipsum

from accounts.models import PermissionSet, User



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

    def test_caseinsensitive_name(self):

        user = User.objects.create(username='user',
                                   password=self.password)

        with self.assertRaises(ValidationError):
            user2 = User.objects.create(username='User',
                                    password=self.password)

    def test_get_by_username(self):
        user = User.objects.create(username='User',
                                   password=self.password)

        user2 = User.objects.get(username='user')
        self.assertEqual(user.pk, user2.pk)
        user2 = User.objects.get(username='User')
        self.assertEqual(user.pk, user2.pk)
