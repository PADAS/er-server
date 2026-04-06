import copy
import datetime
import random

import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant

from django.contrib.auth.models import ContentType, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

import accounts.views as views
from accounts.backends import AccountsModelBackend
from accounts.models import PermissionSet, User
from core.tests import BaseAPITest
from factories import PermissionSetFactory, UserFactory


def random_string(length=10):
    return "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for x in range(length)])


def make_one_user():
    user_name = random_string()
    return User.objects.create_user(username=user_name, password=user_name, email=f"{user_name}@email.com")


def make_n_users(n=1):
    return [make_one_user() for x in range(n)]


def make_n_permissionsets(n=1):
    return [PermissionSet.objects.create(name=random_string()) for x in range(n)]


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestTenantPermissionSets:

    @pytest.fixture
    def view_subjects_permission_set_five_tenants(
        self, view_subjects_permission_set, view_subject_permissions, five_tenants
    ):
        five_tenants = list(five_tenants)
        permission_sets = []
        previous_tenant = get_current_tenant()

        try:
            for tenant in five_tenants:
                set_current_tenant(tenant)
                permission_set = PermissionSetFactory.create(
                    das_tenant=tenant, id=view_subjects_permission_set.id, permissions=view_subject_permissions
                )
                permission_sets.append(permission_set)
        finally:
            set_current_tenant(previous_tenant)
        return permission_sets

    def test_two_tenants_sharing_common_permissionset_id(
        self, view_subjects_permission_set, view_subjects_permission_set_five_tenants, five_tenants
    ):
        current_tenant = self.das_tenant
        set_current_tenant(current_tenant)

        #  we are confirming an issue with the PermissionSet model where the same permissionset.id
        #  is being used across multiple tenants for some older default permissionsets resulting in
        #  duplicate permissions when we use the permissions accessor on the permissionset object
        permissions = list(view_subjects_permission_set.permissions.all())

        # given the permissions list, detect duplicate permissions in the list on the permission.id field
        duplicate_permissions = [permission for permission in permissions if permissions.count(permission) > 1]
        assert len(duplicate_permissions) > 0

        # now we force the tenant filtering on the permissionset through table
        permissions = list(view_subjects_permission_set.permissions.filter(permission_sets__das_tenant=current_tenant))

        duplicate_permissions = [permission for permission in permissions if permissions.count(permission) > 1]
        assert len(duplicate_permissions) == 0

    @pytest.fixture
    def user_with_view_subject_only_ps(self, view_subject_permissions):
        """User in the current tenant whose PermissionSet contains only view_subject."""
        user = UserFactory.create()
        ps = PermissionSetFactory.create(permissions=[view_subject_permissions[1]])  # view_subject only
        user.permission_sets.add(ps)
        return user, ps

    @pytest.fixture
    def cross_tenant_copies_with_extra_perm(
        self, user_with_view_subject_only_ps, view_subject_permissions, five_tenants
    ):
        """Same PermissionSet UUID exists in five other tenants, but with view_subjectgroup instead."""
        user, ps = user_with_view_subject_only_ps
        previous_tenant = get_current_tenant()
        try:
            for tenant in list(five_tenants):
                set_current_tenant(tenant)
                PermissionSetFactory.create(
                    das_tenant=tenant,
                    id=ps.id,
                    permissions=[view_subject_permissions[0]],  # view_subjectgroup only
                )
        finally:
            set_current_tenant(previous_tenant)
        return user

    def test_get_group_permissions_does_not_leak_cross_tenant_permissions(self, cross_tenant_copies_with_extra_perm):
        """get_group_permissions must not return permissions from other tenants' PermissionSetPermission
        rows when a PermissionSet UUID is shared across tenants (legacy default permissionsets)."""
        set_current_tenant(self.das_tenant)
        user = cross_tenant_copies_with_extra_perm
        backend = AccountsModelBackend()
        perms = backend.get_group_permissions(user)

        assert "observations.view_subject" in perms
        # view_subjectgroup only exists in the other tenants' copies — must not bleed through
        assert "observations.view_subjectgroup" not in perms


class BaseTestCase(TestCase):
    def setUp(self):
        self.all_set = PermissionSet.objects.create(name="all")
        self.some_set = PermissionSet.objects.create(name="some")

        self.all_set.children.add(self.some_set)


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class PermissionSetTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.content_type = ContentType.objects.get(app_label="auth", model="permission")

    def test_some_is_member_of_all(self):
        all_set = PermissionSet.objects.get(name="all")
        some_set = PermissionSet.objects.get(name="some")

        self.assertIn(some_set, all_set.children.all())
        self.assertIn(all_set.id, some_set.get_ancestor_ids())

    def test_user_permissions(self):
        user = make_one_user()
        user_ps = make_n_permissionsets()[0]
        user_permission = Permission.objects.create(
            name="User permission", codename="user_perm", content_type=self.content_type
        )
        user_ps.permissions.add(user_permission)
        user.permission_sets.add(user_ps)

        self.assertIn(user_ps, user.get_all_permission_sets())
        self.assertIn(self.content_type.app_label + "." + user_permission.codename, user.get_all_permissions())
        self.assertTrue(user.has_perm(self.content_type.app_label + "." + user_permission.codename))

    def test_2_level_permissionset_hierarchy(self):
        parent_user, child_user = make_n_users(2)
        parent_ps, child_ps = make_n_permissionsets(2)

        parent_permission = Permission.objects.create(
            name="Parent permission", codename="parent_perm", content_type=self.content_type
        )
        parent_ps.permissions.add(parent_permission)
        parent_user.permission_sets.add(parent_ps)

        child_permission = Permission.objects.create(
            name="Child permission", codename="child_perm", content_type=self.content_type
        )
        child_permission.permission_sets.add(child_ps)
        child_user.permission_sets.add(child_ps)

        self.assertIn(parent_ps, parent_user.get_all_permission_sets())
        self.assertIn(self.content_type.app_label + "." + parent_permission.codename, parent_user.get_all_permissions())

        self.assertIn(child_ps, child_user.get_all_permission_sets())
        self.assertIn(self.content_type.app_label + "." + child_permission.codename, child_user.get_all_permissions())
        self.assertNotIn(parent_ps, child_user.get_all_permission_sets())

        parent_ps.children.add(child_ps)
        self.assertIn(parent_ps, child_user.get_all_permission_sets())

    def test_3_level_permissionset_hierarchy(self):
        gp_user, parent_user, child_user = make_n_users(3)
        gp_ps, parent_ps, child_ps = make_n_permissionsets(3)

        gp_user.permission_sets.add(gp_ps)
        parent_user.permission_sets.add(parent_ps)
        child_user.permission_sets.add(child_ps)

        self.assertNotIn(gp_ps, parent_user.get_all_permission_sets())
        self.assertNotIn(gp_ps, child_user.get_all_permission_sets())
        self.assertNotIn(parent_ps, child_user.get_all_permission_sets())

        gp_ps.children.add(parent_ps)
        parent_ps.children.add(child_ps)

        self.assertIn(gp_ps, parent_user.get_all_permission_sets())
        self.assertIn(gp_ps, child_user.get_all_permission_sets())
        self.assertIn(parent_ps, child_user.get_all_permission_sets())


class UserModelTest(TestCase):
    password = User.objects.make_random_password()
    user_const = dict(last_name="last", first_name="first")

    def test_caseinsensitive_name(self):
        User.objects.create(username="user", password=self.password, email="user@test.com", **self.user_const)

        with self.assertRaises(ValidationError):
            User.objects.create(username="User", email="user2@test.com", password=self.password, **self.user_const)

    def test_get_by_username(self):
        user = User.objects.create(username="User", email="user3@test.com", password=self.password, **self.user_const)

        user2 = User.objects.get(username="user")
        self.assertEqual(user.pk, user2.pk)
        user2 = User.objects.get(username="User")
        self.assertEqual(user.pk, user2.pk)

    def test_delete_user(self):
        username = random_string(length=15)
        email = f"{random_string()}@{random_string()}.org"
        password = f"{random_string(length=20)}9$"
        newuser = User.objects.create(username=username, email=email, password=password, **self.user_const)

        newuser = User.objects.get(id=newuser.id)

        self.assertIsNotNone(newuser, "expect a user object, but newuser is None")
        User.objects.filter(id=newuser.id).delete()


class TestAuthentication(BaseAPITest):
    password = User.objects.make_random_password()
    user_const = dict(last_name="last", first_name="first")

    def setUp(self):
        super().setUp()

        nologin_const = copy.copy(self.user_const)
        nologin_const["is_nologin"] = True
        self.nologin_user = User.objects.create_user(
            "nologin_user", "das_nologin_user@vulcan.com", self.password, **nologin_const
        )

        self.joc_supervisor = User.objects.create_user(
            "joc_supervisor", "das_joc_supervisor@vulcan.com", self.password, **self.user_const
        )
        self.joc_supervisor.act_as_profiles.add(self.nologin_user)

        staff_const = copy.copy(self.user_const)
        staff_const["is_staff"] = True
        self.staff_user = User.objects.create_user(
            "staff_user", "das_staff_user@vulcan.com", self.password, **staff_const
        )

        self.super_user = User.objects.create_superuser(
            "super_user", "das_super_user@vulcan.com", self.password, **self.user_const
        )

    def test_not_allow_nologin_user(self):
        token = self.create_access_token(self.nologin_user)

        response = self.client.get(
            self.api_base + "/user/me", HTTP_AUTHORIZATION=self.create_authorization_header(token)
        )
        assert response.status_code == 403

    def test_act_as_nologin_user(self):
        request = self.factory.get(self.api_base + "/user/me")
        request.META["HTTP_USER_PROFILE"] = str(self.nologin_user.pk)
        self.force_authenticate(request, self.joc_supervisor)

        response = views.UserView.as_view()(request, id="me")
        self.assertEqual(response.status_code, 200)

    def test_fail_act_as_superuser(self):
        token = self.create_access_token(self.joc_supervisor)
        with self.assertRaises(PermissionDenied):
            response = self.client.get(
                self.api_base + "/user/me",
                HTTP_AUTHORIZATION=self.create_authorization_header(token),
                HTTP_USER_PROFILE=str(self.super_user.pk),
            )

    def test_allow_using_profile_of_self(self):
        token = self.create_access_token(self.joc_supervisor)

        response = self.client.get(
            self.api_base + "/user/me",
            HTTP_AUTHORIZATION=self.create_authorization_header(token),
            HTTP_USER_PROFILE=str(self.joc_supervisor.pk),
        )
        assert response.status_code == 200

    def test_fail_act_as_unlisted_user(self):
        token = self.create_access_token(self.joc_supervisor)
        with self.assertRaises(PermissionDenied):
            response = self.client.get(
                self.api_base + "/user/me",
                HTTP_AUTHORIZATION=self.create_authorization_header(token),
                HTTP_USER_PROFILE=str(self.staff_user.pk),
            )

    def test_expired_token_returns_401(self):
        expires = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=1)
        token = self.create_access_token(self.joc_supervisor, expires=expires)
        response = self.client.get(
            self.api_base + "/user/me", HTTP_AUTHORIZATION=self.create_authorization_header(token)
        )

        assert response.status_code == 401
