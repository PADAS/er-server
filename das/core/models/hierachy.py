from typing import Union

from django_multitenant.fields import TenantForeignKey
from django_multitenant.models import TenantModelMixin

from django.apps import apps
from django.db import models
from django.db.models.fields.related import lazy_related_operation

from core.models import DASTenant
from core.models.core import HierarchyManager, UUIDModel
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager


class TenantHierarchyChildrenHelpers:
    def natural_key(self):
        return (self._from, self.to)


def create_tenanthierarchychildren_model(
    model: Union[models.Model, str],
    through_fieldname: str = "children",
) -> models.Model:
    """Similar to what the manytomany field does in automatically creating a through table,
    but we are doing this for our tenant enabled hierarchy children through table
    see: create_many_to_many_intermediary_model found in django/db/models/fields/related.py

    Args:
        model (Union[models.Model, str]): the model we are making the through table for
        through_fieldname (str): the many2many fieldname, default is "children"

    Returns:
        models.Model: _description_
    """
    if isinstance(model, str):
        model = apps.get_model(model)

    def set_managed(model, related, through):
        through._meta.managed = model._meta.managed or related._meta.managed

    name = f"{model.__name__.lower()}children"
    class_name = f"{model.__name__}Children"
    db_table = f"{model._meta.app_label.lower()}_{name}"
    from_name = f"from_{model.__name__.lower()}"
    to_name = f"to_{model.__name__.lower()}"

    lazy_related_operation(set_managed, model, model, name)

    meta = type(
        "Meta",
        (),
        {
            "db_table": db_table,
            "app_label": model._meta.app_label,
            "apps": model._meta.apps,
            "db_tablespace": model._meta.db_tablespace,
            "unique_together": ("das_tenant", from_name, to_name),
            "base_manager_name": "objects",
            "default_manager_name": "objects",
        },
    )

    attrs = {
        f"from_{model.__name__.lower()}": TenantForeignKey(
            model,
            on_delete=models.CASCADE,
            db_column=f"from_{model.__name__.lower()}_id",
            db_constraint=getattr(model, through_fieldname).field.remote_field.db_constraint,
            related_name="self",
        ),
        f"to_{model.__name__.lower()}": TenantForeignKey(
            model,
            on_delete=models.CASCADE,
            db_column=f"to_{model.__name__.lower()}_id",
            db_constraint=getattr(model, through_fieldname).field.remote_field.db_constraint,
            related_name="children_to",
        ),
        "das_tenant": models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id),
        "tenant_id": "das_tenant_id",
        "objects": CommonTenantManager(),
        "Meta": meta,
        "__module__": model.__module__,
    }

    return type(
        class_name,
        (TenantModelMixin, UUIDModel, TenantHierarchyChildrenHelpers),
        attrs,
    )


class TenantHierarchyModel(TenantModelMixin, models.Model):
    """
    Provides a recursive hierarchy on self.
    A child can have multiple parents.
    These access functions are used by other recursive Mixins.
    workaround:
    Django does not support a dynamic name for the through class in a ManyToManyfield like for other
    fields. It does support a dynamic name for the related_name property. Since it cannot, we require the subclasser of TenantHierarchyModel to declare the
    "children" property in their derived classe. Then provide a prescriptive model in the through field
    that has been derived from TenantHiearchyChildren
    see https://code.djangoproject.com/ticket/11760 for more information

    Define children in your derived class:
    children = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="_parents",
        through="%(class)s_TenantHierarchyChildren",
    )
    """

    class Meta:
        abstract = True

    objects = HierarchyManager()

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    def parents(self):
        return self.__class__.objects.filter(children=self)

    def get_ancestors(self):
        return self.__class__.objects.get_ancestors(self)

    def get_descendants(self):
        return self.__class__.objects.get_descendants(self)

    def get_ancestor_ids(self):
        return [a.id for a in self.get_ancestors()]
