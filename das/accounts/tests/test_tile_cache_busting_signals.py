"""Tests for the per-user vector-tile cache-busting signals (ERA-11809).

These signals invalidate a single user's cached event tiles when their identity
or permissions change:
- ``AccessToken`` ``post_delete`` (token revocation)
- ``User.permission_sets`` membership change (``m2m_changed``)
- ``PermissionSetPermission`` ``post_save`` / ``post_delete`` (set contents change)
"""

from __future__ import annotations

import pytest

from django.contrib.auth.models import Permission
from django.core.cache import caches

from accounts.models.permissionset import PermissionSet
from accounts.tile_cache import bump_user_tile_version, get_user_tile_version
from factories import AccessTokenFactory


@pytest.fixture(autouse=True)
def _clear_vector_tile_cache():
    caches["vector_tiles"].clear()
    yield
    caches["vector_tiles"].clear()


def _version(user) -> int:
    return get_user_tile_version(str(user.das_tenant_id), str(user.id))


class TestUserTileVersionCounter:
    """Unit behavior of the per-user (identity) version counter in accounts.tile_cache."""

    def test_unbumped_version_is_zero(self):
        assert get_user_tile_version("tenant-x", "user-x") == 0

    def test_bump_increments_version(self):
        bump_user_tile_version("tenant-y", "user-y")
        assert get_user_tile_version("tenant-y", "user-y") == 1
        bump_user_tile_version("tenant-y", "user-y")
        assert get_user_tile_version("tenant-y", "user-y") == 2

    def test_versions_isolated_per_user_and_tenant(self):
        bump_user_tile_version("tenant-z", "user-a")
        assert get_user_tile_version("tenant-z", "user-a") == 1
        # Different user, same tenant — independent.
        assert get_user_tile_version("tenant-z", "user-b") == 0
        # Same user id, different tenant — independent.
        assert get_user_tile_version("tenant-other", "user-a") == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestTokenDeleteBusting:
    def test_token_delete_bumps_user_version(self, user, application):
        token = AccessTokenFactory.create(user=user, application=application)
        before = _version(user)
        token.delete()
        assert _version(user) == before + 1


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestMembershipChangeBusting:
    def test_adding_membership_bumps_user(self, user, das_tenant):
        perm_set = PermissionSet.objects.create(name="member_bump_set", das_tenant=das_tenant)
        before = _version(user)
        user.permission_sets.add(perm_set)
        assert _version(user) > before

    def test_removing_membership_bumps_user(self, user, das_tenant):
        perm_set = PermissionSet.objects.create(name="member_remove_set", das_tenant=das_tenant)
        user.permission_sets.add(perm_set)
        mid = _version(user)
        user.permission_sets.remove(perm_set)
        assert _version(user) > mid

    def test_membership_change_does_not_bump_other_user(self, user, create_user, das_tenant):
        other = create_user(username="unaffected_member_user")
        perm_set = PermissionSet.objects.create(name="member_isolated_set", das_tenant=das_tenant)
        other_before = _version(other)
        user.permission_sets.add(perm_set)
        assert _version(other) == other_before

    def test_forward_clear_bumps_user(self, user, das_tenant):
        """``user.permission_sets.clear()`` must bust that user's tiles."""
        perm_set = PermissionSet.objects.create(name="member_forward_clear_set", das_tenant=das_tenant)
        user.permission_sets.add(perm_set)
        mid = _version(user)
        user.permission_sets.clear()
        assert _version(user) > mid

    def test_reverse_clear_bumps_members(self, user, das_tenant):
        """``permission_set.user_set.clear()`` must bust every member's tiles.

        Regression: ``post_clear`` carries ``pk_set=None`` in both directions, so
        the clear path is handled in ``pre_clear`` to capture members first.
        """
        perm_set = PermissionSet.objects.create(name="member_reverse_clear_set", das_tenant=das_tenant)
        user.permission_sets.add(perm_set)
        mid = _version(user)
        perm_set.user_set.clear()
        assert _version(user) > mid

    def test_reverse_clear_does_not_bump_non_member(self, user, create_user, das_tenant):
        """Clearing a set's members must not bust an unrelated user's tiles."""
        other = create_user(username="unaffected_reverse_clear_user")
        perm_set = PermissionSet.objects.create(name="member_reverse_clear_isolated_set", das_tenant=das_tenant)
        user.permission_sets.add(perm_set)
        other_before = _version(other)
        perm_set.user_set.clear()
        assert _version(other) == other_before


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestPermissionSetContentsBusting:
    def test_adding_permission_to_set_bumps_members(self, user, das_tenant):
        perm_set = PermissionSet.objects.create(name="contents_bump_set", das_tenant=das_tenant)
        user.permission_sets.add(perm_set)
        before = _version(user)
        perm = Permission.objects.filter(content_type__app_label="auth").first()
        perm_set.permissions.add(perm)
        assert _version(user) > before

    def test_removing_permission_from_set_bumps_members(self, user, das_tenant):
        perm_set = PermissionSet.objects.create(name="contents_remove_set", das_tenant=das_tenant)
        user.permission_sets.add(perm_set)
        perm = Permission.objects.filter(content_type__app_label="auth").first()
        perm_set.permissions.add(perm)
        mid = _version(user)
        perm_set.permissions.remove(perm)
        assert _version(user) > mid
