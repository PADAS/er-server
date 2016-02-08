
import django.db.models as models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import Permission

from accounts.models import PermissionSet


class PermissionSetGroupMixin(object):
    group_attr_name = 'group'

    def get_obj_permission_set_ids(self, obj=None):
        """
        Returns a set of permission set ids of all permission sets
        assigned to this object
        """
        return getattr(self, self.group_attr_name).get_obj_permission_set_ids(obj)


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

    def get_obj_permission_set_ids(self, obj=None):
        """
        Returns a set of permission set ids of all permission sets
        assigned to this object
        """
        if not hasattr(obj, '_obj_perm_cache'):
            all_ps = set()
            direct_ps = self.permission_sets.all()

            for ps in direct_ps:
                all_ps.add(ps.id)
                all_ps.add(ps.get_ancestor_ids())
            obj._obj_perm_cache = all_ps
        return obj._obj_perm_cache


class PermissionSetHierarchyMixin(PermissionSetMixin):
    """
    PermissionSetHierarchyMixin relates the inheriting group class to the DAS Permissions system.
    Specifically, it creates a foreign key relationships with the PermissionSet table,
    and adds some model functions for discovering object level permissions.

    """

    class Meta:
        abstract = True

    def get_obj_permission_set_ids(self, obj=None):
        """
        Returns a set of permission ids that this object has has through the group and
        group ancestors.
        .
        """
        if not hasattr(obj, '_obj_perm_hierarchy_cache'):
            all_ps = set()

            for g in self.get_ancestors(include_self=True):
                direct_ps = g.permission_sets.all()

                for ps in direct_ps:
                    all_ps.add(ps.id)
                    all_ps.update(ps.get_ancestor_ids())
            obj._obj_perm_hierarchy_cache = all_ps

        return obj._obj_perm_hierarchy_cache
