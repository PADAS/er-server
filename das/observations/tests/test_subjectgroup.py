import json
from uuid import uuid4

from django.contrib.auth.models import Permission

from accounts.models import User, PermissionSet
from core.tests import BaseAPITest
from observations.admin import SubjectGroupChangeForm
from observations.models import Subject, SubjectGroup
from observations.views import SubjectGroupsView, SubjectsView

API_BASE = '/api/v1.0'


def make_perm(perm):
    return "{0}.{1}".format(perm.content_type.app_label, perm.codename)


class SubjectGroupTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        subject_view = PermissionSet.objects.create(
            name='subject_view')
        subject_view.permissions.add(Permission.objects.get_by_natural_key(
            'view_subject', 'observations', 'subject'
        ))
        subject_view.permissions.add(Permission.objects.get_by_natural_key(
            'view_subjectgroup', 'observations', 'subjectgroup'
        ))
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user(
            'super', 'super@test.com', 'super', is_staff=True, **user_const)
        self.user.permission_sets.add(subject_view)
        self.user.save()
        # Create both types of subjects(active & inactive)
        self.henry = Subject.objects.create(name='Henry')
        self.rosie = Subject.objects.create(name='Rosie')
        self.alpha = Subject.objects.create(name='Alpha', is_active=False)
        self.beta = Subject.objects.create(name='beta', is_active=False)
        # Create SubjectGroup and link subjects  using SubjectGroupChangeForm
        subject_group_data = {
            "id": uuid4(),
            "name": "Lewa Elephants",
            "active_subjects": [self.henry.id, self.rosie.id],
            "inactive_subjects": [self.alpha.id, self.beta.id],
            "permission_sets": [subject_view],
            "is_visible": True
        }
        form = SubjectGroupChangeForm(data=subject_group_data)
        self.assertTrue(form.is_valid())
        form.save()

    def test_subjectgroup(self):
        subject_group = SubjectGroup.objects.get(name='Lewa Elephants')
        lewa_elephants = subject_group.get_all_subjects()
        # Check inactive subjects are in subject group's subject list
        self.assertTrue(
            self.alpha in lewa_elephants and self.beta in lewa_elephants
        )

    def test_subject_groups_api(self):
        # Test subjectgroups api(lists subjectgroups and linked subjects)
        # whether this api returns inactive subjects of subjectgroups
        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        subject_ids = []
        for subject_group in response.data:
            for subject in subject_group.get('subjects'):
                subject_ids.append(subject.get('id'))
        self.assertTrue((str(self.alpha.id) not in subject_ids and
                         str(self.beta.id) not in subject_ids) and
                        (str(self.rosie.id) in subject_ids and
                         str(self.henry.id) in subject_ids))

    def test_subjects_api(self):
        # Test subjects api(lists all active subjects)
        # whether this api returns inactive subject/s or not
        request = self.factory.get(API_BASE + '/subjects')
        self.force_authenticate(request, self.user)

        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        subject_ids = []
        for subject in response.data:
            subject_ids.append(subject.get('id'))
        self.assertTrue((str(self.alpha.id) not in subject_ids and
                         str(self.beta.id) not in subject_ids) and
                        (str(self.rosie.id) in subject_ids and
                         str(self.henry.id) in subject_ids))


class SubjectGroupSubGroupsPermissionsTest(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self) -> None:
        super().setUp()
        self.view_subject_group_perm_name = 'view_subjectgroup'
        self.child_grp_1 = SubjectGroup.objects.create(name='Child Group 1')
        self.child_grp_2 = SubjectGroup.objects.create(name='Child Group 2')
        self.parent_group = SubjectGroup.objects.create(name='Parent Group')

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
        self.parent_group.save()

        self.user = User.objects.create_user(username='active_user',
                                             email='active_user@test.com',
                                             password=User.objects.make_random_password(),
                                             **self.user_const)
        self.view_subject_perm = Permission.objects.get(
            codename=self.view_subject_group_perm_name)
        self.perm_set = PermissionSet.objects.create(name="View child 1 Perm set")

    def test_all_subgroups_not_visible_whn_granted_access_to_one_subgroup(self):

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.user.permission_sets.add(self.perm_set)

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        self.assertFalse(
            self.user.has_perm(make_perm(self.view_subject_perm), self.child_grp_2))

    def test_get_subjectgroups_for_user_with_perms_for_child_1_group(self):
        """
        when the user only has permissions to view only child group 1
        only child group one should be returned by the api
        the child group should be in the top level subject groups
        """

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.user.permission_sets.add(self.perm_set)

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        self.assertIn(str(self.child_grp_1.id), [subjectgroup.get('id') for subjectgroup in response.data])
        subject_group_ids = []
        for subject_group in response.data:
            subject_group_ids.append(subject_group.get('id'))
            for subgroup in subject_group.get('subgroups'):
                subject_group_ids.append(subgroup.get('id'))
        self.assertNotIn(str(self.child_grp_2.id), subject_group_ids)
        self.assertNotIn(str(self.parent_group.id), subject_group_ids)

    def test_get_subjectgroups_for_user_with_perms_for_parent_group(self):

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.user.permission_sets.add(self.perm_set)

        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_subject_groups_ids = []
        subgroups_ids = []

        for subject_group in response.data:
            top_level_subject_groups_ids.append(subject_group.get('id'))
            for subgroup in subject_group.get('subgroups'):
                subgroups_ids.append(subgroup.get('id'))

        self.assertEqual(str(self.parent_group.id), top_level_subject_groups_ids[0])
        self.assertIn(str(self.child_grp_1.id), subgroups_ids)
        self.assertIn(str(self.child_grp_2.id), subgroups_ids)



