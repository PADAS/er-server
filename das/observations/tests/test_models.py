from django.test import TestCase
from django.contrib.auth.models import Permission
from accounts.models import PermissionSet, User
from observations.models import SubjectGroup, Subject


def make_perm(perm):
    return "{0}.{1}".format(perm.content_type.app_label, perm.codename)

class SubjectGroupTestCase(TestCase):
    def setUp(self):
        all_set = PermissionSet.objects.create(name='all')
        some_set = PermissionSet.objects.create(name='some')

        some_set.parent = all_set
        some_set.save()

    def test_subject_in_group(self):
        ele = Subject.objects.create(name='ele', additional={})
        ele_group = SubjectGroup.objects.create(name='ele_group')

        ele.group = ele_group
        ele.save()

        self.assertEquals(ele.group, ele_group)


class SubjectPermissionsTestCase(TestCase):
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')
        self.view_last_position_name = 'view_last_position'

        self.view_last_position = Permission.objects.get(codename=self.view_last_position_name)

        self.some_set.parent = self.all_set
        self.some_set.permissions.add(Permission.objects.get(codename=self.view_last_position_name))
        self.some_set.save()

        self.superuser = User.objects.create_superuser('admin', 'admin@test.com',
                                                   'admin')
        self.user = User.objects.create_user('joe', 'joe@example.com', 'joe')


    def test_user_has_view_permission(self):
        user = User.objects.create(username='active_user')

        user.permission_sets.add(self.some_set)
        user.save()

        ele = Subject.objects.create(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name='ele_group')
        ele.group = ele_group
        ele.save()

        ele_group.permission_sets.add(self.some_set)
        ele_group.save()

        self.assertTrue(user.has_perm(make_perm(self.view_last_position), ele))

        #view_perm = Permission.objects.get()


class SubjectAlertTestCase(TestCase):
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')

        self.some_set.parent = self.all_set
        self.some_set.save()


    def test_return_user(self):
        user = User.objects.create(username='active_user')
        user.permission_sets.add(self.some_set)
        user.permission_sets.add(self.all_set)
        user.save()

        user2 = User.objects.create(username='no_alert')

        ele = Subject.objects.create(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name='ele_group')
        ele.group = ele_group
        ele.save()

        ele_group.permission_sets.add(self.some_set)
        ele_group.save()

        self.assertIn(user, ele.get_users_to_notify())
        self.assertNotIn(user2, ele.get_users_to_notify())