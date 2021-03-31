from uuid import uuid4
from unittest import mock
from django.db import transaction
from django.db.utils import IntegrityError

from django.contrib.auth.models import Permission
from django.test import TestCase

from accounts.models import User, PermissionSet
from core.tests import BaseAPITest, fake_get_pool, API_BASE
from observations.admin import SubjectGroupChangeForm
from observations.models import Subject, SubjectGroup
from observations.views import SubjectGroupsView, SubjectsView, SubjectGroupView


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

    def test_subject_group_search_api(self):
        request = self.factory.get(API_BASE + "/subjectgroups?group_name=Lewa")
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        assert response.status_code == 200
        for sg in response.data:
            assert "Lewa" in sg['name']

    def test_flat_subject_groups_api(self):
        # Test subjectgroups api(lists flat subjectgroups)
        subject_group = SubjectGroup.objects.get(name='Lewa Elephants')
        child_group = SubjectGroup.objects.create(
            name='Lewa Elephants child group')
        subject_group.children.add(child_group)

        request = self.factory.get(API_BASE + '/subjectgroups?flat=true')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        assert response.status_code == 200
        for sg in response.data:
            assert "subgroups" not in sg
            assert sg['name'] in (subject_group.name, child_group.name)

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

    def test_cyclic_subjectgroup_and_guard_infinite_recursion(self):

        sgrp1 = SubjectGroup.objects.create(name='Subject Group 1')
        sgrp2 = SubjectGroup.objects.create(name='Subject Group 2')
        sgrp3 = SubjectGroup.objects.create(name='Subject Group 3')
        sgrp4 = SubjectGroup.objects.create(name='Subject Group 4')

        sgrp1.children.add(sgrp2)
        sgrp2.children.add(sgrp1, sgrp3)
        sgrp3.children.add(sgrp2)
        sgrp4.children.add(sgrp3)

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)
        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        sgrp1_pk = sgrp1.id  # forms a cyclic graph.
        request = self.factory.get(API_BASE + f'/subjectgroup/{sgrp1_pk}/')
        self.force_authenticate(request, self.user)
        response = SubjectGroupView.as_view()(request, id=str(sgrp1_pk))
        self.assertEqual(response.status_code, 404)

    def test_there_is_default_subject_group(self):
        sg = SubjectGroup.objects.filter(is_default=True)
        self.assertTrue(sg.exists())

    def test_cant_have_two_default_subject_group(self):
        with self.assertRaises(Exception) as raised:
            SubjectGroup.objects.create(name=1, is_default=True)
        self.assertEqual(IntegrityError, type(raised.exception))


class SubjectGroupSubGroupsPermissionsTest(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self) -> None:
        super().setUp()
        self.view_subject_group_perm_name = 'view_subjectgroup'
        self.child_grp_1 = SubjectGroup.objects.create(name='Child Group 1')
        self.child_grp_2 = SubjectGroup.objects.create(name='Child Group 2')
        self.parent_group = SubjectGroup.objects.create(name='Parent Group')

        self.user = User.objects.create_user(username='active_user',
                                             email='active_user@test.com',
                                             password=User.objects.make_random_password(),
                                             **self.user_const)
        self.view_subject_perm = Permission.objects.get(
            codename=self.view_subject_group_perm_name)
        self.perm_set = PermissionSet.objects.create(name="View Subject Group")

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.user.permission_sets.add(self.perm_set)
        self.user.save()

    def test_get_subjgroups_for_user_with_perms_for_child_1_group_returns_child_grp_1_only(self):
        """
        when the user only has permissions to view only child group 1
        only child group one should be returned by the api
        the child group should be in the top level subject groups
        """

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        self.assertIn(str(self.child_grp_1.id), [
                      subjectgroup.get('id') for subjectgroup in response.data])
        subject_group_ids = []
        for subject_group in response.data:
            subject_group_ids.append(subject_group.get('id'))
            for subgroup in subject_group.get('subgroups'):
                subject_group_ids.append(subgroup.get('id'))
        self.assertNotIn(str(self.child_grp_2.id), subject_group_ids)
        self.assertNotIn(str(self.parent_group.id), subject_group_ids)

    def test_get_subjectgroups_for_user_with_perms_for_parent_group_returns_all_children(self):

        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
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

        self.assertEqual(str(self.parent_group.id),
                         top_level_subject_groups_ids[0])
        self.assertIn(str(self.child_grp_1.id), subgroups_ids)
        self.assertIn(str(self.child_grp_2.id), subgroups_ids)

    def test_user_gets_only_child_groups_if_they_have_perms_but_no_perms_for_parent(self):
        """
        test that a user can view both child group 1 and child group 2 when they
        have permissions to view both groups
        """
        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        self.child_grp_2.permission_sets.add(self.perm_set)
        self.child_grp_2.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_subject_groups_ids = []

        for subject_group in response.data:
            top_level_subject_groups_ids.append(subject_group.get('id'))

        self.assertIn(str(self.child_grp_1.id), top_level_subject_groups_ids)
        self.assertIn(str(self.child_grp_2.id), top_level_subject_groups_ids)

    def test_user_with_perm_to_view_parent_and_child1_only_views_those_two(self):
        """
        create a parent group, add child_1 and child_2 to the parent group.
        Give the user permissions to view the parent group and child 1 but not
        child_2.

        Result: User should see both subjects under parent group A because
        membership goes down the hierarchy. if a user can see parent A, t
        hen can see all of the children of A
        """

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
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

        self.assertIn(str(self.parent_group.id), top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_1.id),
                         top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_2.id),
                         top_level_subject_groups_ids)
        self.assertIn(str(self.child_grp_1.id), subgroups_ids)
        self.assertIn(str(self.child_grp_2.id), subgroups_ids)
        self.assertNotIn(str(self.parent_group.id), subgroups_ids)

    def test_user_only_sees_child_1_if_they_have_no_permissions_to_view_parent_and_child2(self):
        """
        Create a group A with two sub-groups, child_grp_1 and child_grp_2.
        Do not give permissions to see A
        Create a permission set that gives rights to child_grp_1 but not child_grp_2.

        Result: User should only see child_grp_1 at the top level
        """

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
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

        self.assertNotIn(str(self.parent_group.id),
                         top_level_subject_groups_ids)
        self.assertIn(str(self.child_grp_1.id), top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_2.id),
                         top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_1.id), subgroups_ids)
        self.assertNotIn(str(self.child_grp_2.id), subgroups_ids)
        self.assertNotIn(str(self.parent_group.id), subgroups_ids)

    def test_user_sees_child_1_and_2_under_parent_only_if_they_have_permissions_on_all_subject_groups(self):
        """
        Create parent A, create child 1 and child 2 and add them to Parent A
        Give user permissions on Parent, child 1 and child 2

        Result: Child 1 and child 2 appear under Parent A
        """
        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        self.child_grp_2.permission_sets.add(self.perm_set)
        self.child_grp_2.save()

        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
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

        self.assertIn(str(self.parent_group.id), top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_1.id),
                         top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_2.id),
                         top_level_subject_groups_ids)
        self.assertIn(str(self.child_grp_1.id), subgroups_ids)
        self.assertIn(str(self.child_grp_2.id), subgroups_ids)
        self.assertNotIn(str(self.parent_group.id), subgroups_ids)

    def test_user_sees_child_1_and_2_at_the_top_level_if_they_have_permissions_for_both_but_not_the_parent(self):

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()

        self.child_grp_2.permission_sets.add(self.perm_set)
        self.child_grp_2.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
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

        self.assertNotIn(str(self.parent_group.id),
                         top_level_subject_groups_ids)
        self.assertIn(str(self.child_grp_1.id), top_level_subject_groups_ids)
        self.assertIn(str(self.child_grp_2.id), top_level_subject_groups_ids)
        self.assertNotIn(str(self.child_grp_1.id), subgroups_ids)
        self.assertNotIn(str(self.child_grp_2.id), subgroups_ids)
        self.assertNotIn(str(self.parent_group.id), subgroups_ids)


class ThreeLevelSubjectGroupHierarchyPermissionsTest(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()
        self.view_subject_group_perm_name = 'view_subjectgroup'
        self.child_grp_1 = SubjectGroup.objects.create(name='Child Group 1')
        self.child_grp_2 = SubjectGroup.objects.create(name='Child Group 2')
        self.parent_group = SubjectGroup.objects.create(name='Parent Group')
        self.grandparent_group = SubjectGroup.objects.create(
            name='Grandparent Group')

        self.user = User.objects.create_user(username='active_user',
                                             email='active_user@test.com',
                                             password=User.objects.make_random_password(),
                                             **self.user_const)
        self.view_subject_perm = Permission.objects.get(
            codename=self.view_subject_group_perm_name)
        self.perm_set = PermissionSet.objects.create(
            name="View Subject Group Perm set")

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.user.permission_sets.add(self.perm_set)
        self.user.save()

    def test_user_has_permissions_to_view_grandparent(self):
        """
        User has permissions to view the Grand Parent group, they should be able
        to view the parent group --> child groups
        """
        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
        self.parent_group.save()

        self.grandparent_group.children.add(self.parent_group)
        self.grandparent_group.permission_sets.add(self.perm_set)
        self.grandparent_group.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_ids = []
        mid_level_ids = []
        bottom_level_ids = []

        for gp_subject_group in response.data:
            top_level_ids.append(gp_subject_group.get('id'))
            for parent_subgroup in gp_subject_group.get('subgroups'):
                mid_level_ids.append(parent_subgroup.get('id'))
                for child_subgroup in parent_subgroup.get('subgroups'):
                    bottom_level_ids.append(child_subgroup.get('id'))

        self.assertIn(str(self.grandparent_group.id), top_level_ids)
        self.assertIn(str(self.parent_group.id), mid_level_ids)
        self.assertIn(str(self.child_grp_1.id), bottom_level_ids)
        self.assertIn(str(self.child_grp_2.id), bottom_level_ids)

        self.assertNotIn(str(self.grandparent_group), mid_level_ids)
        self.assertNotIn(str(self.grandparent_group), bottom_level_ids)

        self.assertNotIn(str(self.parent_group.id), top_level_ids)
        self.assertNotIn(str(self.parent_group.id), bottom_level_ids)

        self.assertNotIn(str(self.child_grp_1), top_level_ids)
        self.assertNotIn(str(self.child_grp_1), mid_level_ids)
        self.assertNotIn(str(self.child_grp_2), top_level_ids)
        self.assertNotIn(str(self.child_grp_2), mid_level_ids)

    def test_user_has_perms_to_view_parent_group_only(self):
        """
        the user has permissions to view only the parent group and not it's
        parent or it's children

        Result: parent group should be at the top level and child groups in the
        mid level
        """
        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.save()

        self.grandparent_group.children.add(self.parent_group)
        self.grandparent_group.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_ids = []
        mid_level_ids = []
        bottom_level_ids = []

        for parent_subject_group in response.data:
            top_level_ids.append(parent_subject_group.get('id'))
            for child_subgroup in parent_subject_group.get('subgroups'):
                mid_level_ids.append(child_subgroup.get('id'))
                for other_sub_group in child_subgroup.get('subgroups'):
                    bottom_level_ids.append(other_sub_group.get('id'))

        self.assertIn(str(self.parent_group.id), top_level_ids)
        self.assertIn(str(self.child_grp_1.id), mid_level_ids)
        self.assertIn(str(self.child_grp_2.id), mid_level_ids)

        self.assertNotIn(str(self.grandparent_group), mid_level_ids)
        self.assertNotIn(str(self.grandparent_group), top_level_ids)

        self.assertNotIn(str(self.parent_group.id), mid_level_ids)

        self.assertNotIn(str(self.child_grp_1), top_level_ids)
        self.assertNotIn(str(self.child_grp_2), top_level_ids)

        self.assertEqual(bottom_level_ids, [])

    def test_user_only_has_permissions_to_view_child_groups(self):
        """
        the user only has permissions to view the child groups

        Result: the child groups should appear in the top level
        """

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.parent_group.children.add(self.child_grp_1, self.child_grp_2)
        self.parent_group.save()

        self.grandparent_group.children.add(self.parent_group)
        self.grandparent_group.save()

        self.child_grp_1.permission_sets.add(self.perm_set)
        self.child_grp_1.save()
        self.child_grp_2.permission_sets.add(self.perm_set)
        self.child_grp_2.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_ids = []
        mid_level_ids = []
        bottom_level_ids = []

        for subject_group in response.data:
            top_level_ids.append(subject_group.get('id'))
            for child_subgroup in subject_group.get('subgroups'):
                mid_level_ids.append(child_subgroup.get('id'))
                for other_sub_group in child_subgroup.get('subgroups'):
                    bottom_level_ids.append(other_sub_group.get('id'))

        self.assertIn(str(self.child_grp_1.id), top_level_ids)
        self.assertIn(str(self.child_grp_2.id), top_level_ids)

        self.assertNotIn(str(self.grandparent_group), mid_level_ids)
        self.assertNotIn(str(self.grandparent_group), top_level_ids)

        self.assertNotIn(str(self.parent_group.id), mid_level_ids)
        self.assertNotIn(str(self.parent_group.id), top_level_ids)

        self.assertEqual(mid_level_ids, [])
        self.assertEqual(bottom_level_ids, [])


class TestSubjectGroupsVisibility(BaseAPITest):
    fixtures = [
        'accounts_choices.json',
        'initial_admin.yaml',
        'iOS_user.yaml',
    ]
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()
        self.superuser = User.objects.get(username='admin')
        self.view_subject_group_perm_name = 'view_subjectgroup'
        self.child_grp = SubjectGroup.objects.create(name='Child Group')
        self.parent_group = SubjectGroup.objects.create(name='Parent Group')

        self.user = User.objects.create_user(username='active_user',
                                             email='active_user@test.com',
                                             password=User.objects.make_random_password(),
                                             **self.user_const)
        self.view_subject_perm = Permission.objects.get(
            codename=self.view_subject_group_perm_name)
        self.perm_set = PermissionSet.objects.create(
            name="View Subject Group Perm set")

        self.perm_set.permissions.add(self.view_subject_perm)
        self.perm_set.save()

        self.user.permission_sets.add(self.perm_set)
        self.user.save()

    def test_view_parent_is_not_visible_but_include_hidden(self):
        """
        Parent group is_visible=False
        Return parent group because user passed in include_hidden

        """
        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.is_visible = False
        self.parent_group.save()

        request = self.factory.get(
            API_BASE + '/subjectgroups?include_hidden=true')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_subject_groups_ids = []

        for subject_group in response.data:
            top_level_subject_groups_ids.append(subject_group.get('id'))

        self.assertIn(str(self.parent_group.id), top_level_subject_groups_ids)

    def test_view_child_groups_if_parent_is_not_visible(self):
        """
        Parent group is_visible=False
        User given rights to see Child group directly

        Result: Child group should be returned
        """
        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.is_visible = False
        self.parent_group.save()

        self.parent_group.children.add(self.child_grp)
        self.parent_group.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_subject_groups_ids = []

        for subject_group in response.data:
            top_level_subject_groups_ids.append(subject_group.get('id'))

        self.assertIn(str(self.child_grp.id), top_level_subject_groups_ids)
        self.assertNotIn(str(self.parent_group.id),
                         top_level_subject_groups_ids)

    def test_view_child_groups_if_parent_is_not_visible_superuser(self):
        """
        Parent group is_visible=False
        User given rights to see Child group directly

        Result: Child group should be returned
        """
        self.parent_group.permission_sets.add(self.perm_set)
        self.parent_group.is_visible = False
        self.parent_group.save()

        self.parent_group.children.add(self.child_grp)
        self.parent_group.save()

        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        top_level_subject_groups_ids = []

        for subject_group in response.data:
            top_level_subject_groups_ids.append(subject_group.get('id'))

        self.assertIn(str(self.child_grp.id), top_level_subject_groups_ids)
        self.assertNotIn(str(self.parent_group.id),
                         top_level_subject_groups_ids)


class TestSubjectGroupAutoCreatedViewPerm(TestCase):
    def create_subject_group(self):
        subject_group = SubjectGroup.objects.create(name='Elephant')
        transaction.get_connection().run_and_clear_commit_hooks()
        permission_set = subject_group.permission_sets.get(
            name=subject_group.auto_permissionset_name)
        self.assertEqual(permission_set.name,
                         subject_group.auto_permissionset_name)
        return subject_group, permission_set

    def test_auto_created_unique_perm_view_subjectgroup(self):
        with mock.patch('django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block',
                        lambda a: False):
            all_perms = {
                'view_subjectgroup',
                'view_real_time',
                'view_subject',
                'subscribe_alerts',
            }
            subject_group, permission_set = self.create_subject_group()
            with self.assertRaisesMessage(Exception, 'PermissionSet matching query does not exist.'):
                subject_group.permission_sets.get(
                    name='view elephant subjectgroup')
            perms_in_permission_set = {
                perm.codename for perm in permission_set.permissions.all()}

            subject_group_has_permission_set = \
                subject_group.permission_sets.filter(
                    name=subject_group.auto_permissionset_name).exists()
            self.assertTrue(subject_group_has_permission_set)
            self.assertTrue(all_perms == perms_in_permission_set)

    def test_view_perm_deleted_when_subject_group_is_deleted(self):
        with mock.patch('django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block',
                        lambda a: False):
            subject_group, permission_set = self.create_subject_group()
            subject_group.delete()
            permission_set = PermissionSet.objects.filter(
                name=subject_group.auto_permissionset_name)
            self.assertEqual(len(permission_set), 0)
