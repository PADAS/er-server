import uuid

from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin

import django.db.models as models
from django.contrib.auth.models import Permission
from django.db.models import UniqueConstraint
from django.utils.translation import gettext_lazy as _

from core.models import DASTenant, HierarchyManager, TimestampedModel, UUIDModel
from core.models.hierachy import (
    TenantHierarchyModel,
    create_tenanthierarchychildren_model,
)
from utils.migrations.columns import default_tenant_id


class PermissionSetManager(HierarchyManager):
    """
    The manager for the accounts PermissionSet model.
    """

    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(**{"name": name})


class PermissionSet(TenantHierarchyModel, TimestampedModel):
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
    name = models.CharField(_("name"), max_length=80)
    permissions = models.ManyToManyField(
        "auth.permission",
        related_name="permission_sets",
        through="accounts.PermissionSetPermission",
        through_fields=("permissionset", "permission"),
    )
    children = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="_parents",
        through="accounts.PermissionSetChildren",
    )

    objects = PermissionSetManager()

    def natural_key(self):
        return (self.name,)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["das_tenant", "name"], name="%(app_label)s_%(class)s_tenant_name_unique"),
        ]
        verbose_name = _("permission set")
        verbose_name_plural = _("permission sets")
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.name


PermissionSetChildren = create_tenanthierarchychildren_model(PermissionSet)


class PermissionSetPermissionManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, permissionset, permission):
        return self.get(permissionset=permissionset, permission=permission)


class PermissionSetPermission(TenantModelMixin, UUIDModel):
    permissionset = TenantForeignKey(PermissionSet, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="%(app_label)s_%(class)s",
    )
    tenant_id = "das_tenant_id"

    objects = PermissionSetPermissionManager()

    def natural_key(self):
        return (self.permissionset, self.permission)
