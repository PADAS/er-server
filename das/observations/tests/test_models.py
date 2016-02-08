from django.test import TestCase
from accounts.models import PermissionSet, User
from observations.models import SubjectGroup


class SubjectGroupTestCase(TestCase):
    def setUp(self):
        all_set = PermissionSet.objects.create(name='all')
        some_set = PermissionSet.objects.create(name='some')

        some_set.parent = all_set
        some_set.save()

    def test_all_is_parent_of_some(self):
        all_set = PermissionSet.objects.get(name='all')
        some_set = PermissionSet.objects.get(name='some')

        self.assertEqual(all_set, some_set.parent)
        self.assertIn(some_set, all_set.get_children())