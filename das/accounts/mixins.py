from itertools import chain

import django.db.models as models
from django.contrib import auth
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from accounts.models.permissionset import PermissionSet


class PermissionSetGroupMixin(object):
    groups_attr_name = 'groups'

    def get_obj_permission_set_ids(self):
        """
        Returns a set of permission set ids of all permission sets
        assigned to this object
        """
        groups = getattr(self, self.groups_attr_name)
        ps_ids = set()
        for group in groups.all():
            ps_ids.update(group.get_obj_permission_set_ids())
        return ps_ids


class PermissionSetMixin(models.Model):
    """
    PermissionSetMixin relates the inheriting class to the DAS Permissions system.
    Specifically, it creates a ManyToMany relationship with the PermissionSet table,
    and adds some model functions for discovering object level permissions.
    """
    class Meta:
        abstract = True

    permission_sets = models.ManyToManyField(
        PermissionSet,
        blank=True,
        help_text=_(
            'The permission sets applied to this table. A user in a permission'
            ' set is granted these permissions.'
        )
    )

    def get_obj_permission_set_ids(self):
        """
        Returns a set of permission set ids of all permission sets
        assigned to this object
        """
        if not hasattr(self, '_obj_perm_cache'):
            all_ps = set()
            direct_ps = self.permission_sets.all()

            for ps in direct_ps:
                all_ps.add(ps.id)
                all_ps.add(ps.get_ancestor_ids())
            self._obj_perm_cache = all_ps
        return self._obj_perm_cache


class PermissionSetHierarchyMixin(PermissionSetMixin):
    """
    PermissionSetHierarchyMixin relates the inheriting group class to the DAS Permissions system.
    Specifically, it creates a foreign key relationships with the PermissionSet table,
    and adds some model functions for discovering object level permissions.

    """

    class Meta:
        abstract = True

    def get_obj_permission_set_ids(self):
        """
        Returns a set of permission ids that this object has through the group and
        group ancestors.
        .
        """
        if not hasattr(self, '_obj_perm_hierarchy_cache'):
            all_ps = set()

            for g in chain(self.get_ancestors(), (self,)):
                direct_ps = g.permission_sets.all()

                for ps in direct_ps:
                    all_ps.add(ps.id)
                    all_ps.update(ps.get_ancestor_ids())
            self._obj_perm_hierarchy_cache = all_ps

        return self._obj_perm_hierarchy_cache


class PermissionsMixin(models.Model):
    """
    A mixin class that adds the fields and methods necessary to support the
    DAS PermissionSet and Permission model using the AccountsModelBackend.
    """
    is_superuser = models.BooleanField(
        _('superuser status'),
        default=False,
        help_text=_(
            'Designates that this user has all permissions without '
            'explicitly assigning them.'
        ),
    )
    permission_sets = models.ManyToManyField(
        PermissionSet,
        blank=True,
        help_text=_(
            'The permission sets this user belongs to. A user will get all permissions '
            'granted to each of their permission sets.'
        ),
    )

    class Meta:
        abstract = True

    def get_user_permissions(self, obj=None):
        """
        Accounts does not assign permissions to a user,
         all permissions come through the permissions sets a user is a member of.
        """
        return set()

    def get_group_permissions(self, obj=None):
        """
        Returns a list of permission strings that this user has through their
        groups. This method queries all available auth backends. If an object
        is passed in, only permissions matching this object are returned.
        """
        permissions = set()
        for backend in auth.get_backends():
            if hasattr(backend, "get_group_permissions"):
                permissions.update(backend.get_group_permissions(self, obj))
        return permissions

    def get_all_permissions(self, obj=None):
        permissions = set()
        for backend in auth.get_backends():
            if hasattr(backend, "get_all_permissions"):
                permissions.update(backend.get_all_permissions(self, obj))
        return permissions

    def has_perm(self, perm, obj=None):
        """
        Returns True if the user has the specified permission. This method
        queries all available auth backends, but returns immediately if any
        backend returns True. Thus, a user who has permission from a single
        auth backend is assumed to have permission in general. If an object is
        provided, permissions for this specific object are checked.
        """

        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True

        # Otherwise we need to check the backends.
        for backend in auth.get_backends():
            if not hasattr(backend, 'has_perm'):
                continue
            try:
                if backend.has_perm(self, perm, obj):
                    return True
            except PermissionDenied:
                return False
        return False

    def has_perms(self, perm_list, obj=None):
        """
        Returns True if the user has each of the specified permissions. If
        object is passed, it checks if the user has all required perms for this
        object.
        """
        for perm in perm_list:
            if not self.has_perm(perm, obj):
                return False
        return True

    def has_any_perms(self, perm_list, obj=None):
        """
        Returns True if the user has any of the specified permissions.
        """
        for perm in perm_list:
            if self.has_perm(perm, obj):
                return True
        return False

    def has_module_perms(self, app_label):
        """
        Returns True if the user has any permissions in the given app label.
        Uses pretty much the same logic as has_perm, above.
        """
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True
        for backend in auth.get_backends():
            if not hasattr(backend, 'has_module_perms'):
                continue
            try:
                if backend.has_module_perms(self, app_label):
                    return True
            except PermissionDenied:
                return False
        return False

    def get_all_permission_sets(self, only_ids=False):
        """
        Returns all permission sets the user is member of AND ascendant permission sets.
        For example, if this user is a member of Group Five, and Group Five is a member of Group A,
        we return Group A and Group Five.
        """
        if self.is_superuser:
            return PermissionSet.objects.all()

        direct_ps = self.permission_sets.all()
        all_ps = set()

        for ps in direct_ps:
            if only_ids:
                all_ps.add(ps.id)
            else:
                all_ps.add(ps)
            ancestors = ps.get_ancestors()
            for ancestor in ancestors:
                if only_ids:
                    all_ps.add(ancestor.id)
                else:
                    all_ps.add(ancestor)
        return all_ps
