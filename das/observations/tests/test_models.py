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
        ele = Subject.objects.create_subject(name='ele', additional={})
        ele_group = SubjectGroup.objects.create(name='ele_group')

        ele.groups.add(ele_group)

        ele = Subject.objects.get(name='ele')
        self.assertIn(ele_group, ele.groups.all())


class SubjectPermissionsTestCase(TestCase):
    user_const = dict(last_name='last', first_name='first')
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')
        self.view_last_position_name = 'view_last_position'

        self.view_last_position = Permission.objects.get(codename=self.view_last_position_name)

        self.some_set.parent = self.all_set
        self.some_set.permissions.add(Permission.objects.get(codename=self.view_last_position_name))
        self.some_set.save()


        self.superuser = User.objects.create_superuser('admin', 'admin@test.com', 'admin', **self.user_const)
        self.user = User.objects.create_user('joe', 'joe@example.com', 'joe', **self.user_const)


    def test_user_has_view_permission(self):
        user = User.objects.create_user(username='active_user', email='active_user@test.com',
                                   password=User.objects.make_random_password(),
                                   **self.user_const)

        user.permission_sets.add(self.some_set)

        ele = Subject.objects.create_subject(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name='ele_group')
        ele.groups.add(ele_group)

        ele_group.permission_sets.add(self.some_set)

        self.assertTrue(user.has_perm(make_perm(self.view_last_position), ele))

        #view_perm = Permission.objects.get()


class SubjectAlertTestCase(TestCase):
    user_const = dict(last_name='last', first_name='first')
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name='all')
        self.some_set = PermissionSet.objects.create(name='some')

        self.some_set.parent = self.all_set
        self.some_set.save()


    def test_return_user(self):
        user = User.objects.create_user(username='active_user', email='active_user@test.com',
                                   password=User.objects.make_random_password(),
                                        **self.user_const)
        user.permission_sets.add(self.some_set)
        user.permission_sets.add(self.all_set)
        user.save()

        user2 = User.objects.create_user(username='no_alert', email='active@test.com',
                                    password=User.objects.make_random_password(),
                                         **self.user_const)

        ele = Subject.objects.create_subject(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name='ele_group')
        ele.groups.add(ele_group)

        ele_group.permission_sets.add(self.some_set)

        self.assertIn(user, ele.get_users_to_notify())
        self.assertNotIn(user2, ele.get_users_to_notify())
