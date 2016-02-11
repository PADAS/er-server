from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from accounts.models import PermissionSet, User



class BaseTestCase(TestCase):
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')

        self.some_set.parent = self.all_set
        self.some_set.save()


class PermissionSetTestCase(BaseTestCase):
    def test_all_is_parent_of_some(self):
        all_set = PermissionSet.objects.get(name='all')
        some_set = PermissionSet.objects.get(name='some')

        self.assertEqual(all_set, some_set.parent)
        self.assertIn(some_set, all_set.get_children())


class ObjectPermissionSetTestCase(BaseTestCase):
    def setUp(self):
        super(ObjectPermissionSetTestCase, self).setUp()

        self.superuser = User.objects.create_superuser('admin', 'admin@test.com',
                                                   'admin')
        self.user = User.objects.create_user('joe', 'joe@example.com', 'joe')

        self.ctype = ContentType.objects.create(
            model='gimlet', app_label='account_tests')
        self.ctype_info = self.ctype._meta.app_label, self.ctype._meta.model_name



    def test_user_has_view_permission(self):
        user = User.objects.create(username='active_user')

        #view_perm = Permission.objects.get()