import uuid

import django.db.models as models
from django.contrib.auth.models import Permission
from django.utils.translation import gettext_lazy as _

from core.models import HierarchyManager, HierarchyModel, TimestampedModel


class PermissionSetManager(HierarchyManager):
    """
    The manager for the accounts PermissionSet model.
    """
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(**{"name": name})


class PermissionSet(HierarchyModel, TimestampedModel):
    """
    PermissionSets are a generic way of categorizing users to apply permissions, or
    some other label, to those users. A user can belong to any number of
    groups.

    A user in a permissionset automatically has all the permissions granted to that
    set. For example, if the group Site editors has the permission
    can_edit_home_page, any user in that set will have that permission.

    Beyond permissions, PermissionSets are a convenient way to categorize users to
    apply some label, or extended functionality, to them. For example, you
    could create a set 'Special users', and you could write code that would
    grant special rights -- such as giving them access to a
    members-only portion of your site, or sending them members-only email
    messages.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=80, unique=True)
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name='permission_sets',
    )

    objects = PermissionSetManager()

    def natural_key(self):
        return (self.name,)

    class Meta:
        verbose_name = _('permission set')
        verbose_name_plural = _('permission sets')

    def __str__(self):
        return self.name
