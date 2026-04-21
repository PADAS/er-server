from django_multitenant.mixins import TenantModelMixin

from django.db import models

from core.models.core import DASTenant, UUIDModel
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager


def create_serial_number_counter_model(model: type[models.Model]) -> type[models.Model]:
    """Build a per-tenant serial-number counter model scoped to ``model``.

    Each consuming model gets its own table (e.g. ``activity_eventserialnumbercounter``),
    so unrelated models never share a counter row. Mirrors the factory pattern
    used by :func:`core.models.hierachy.create_tenanthierarchychildren_model`:
    the class is constructed at import time and must be bound to a module-level
    name in the consuming app so Django's ``ModelBase`` metaclass registers it
    with the app registry and ``makemigrations`` discovers it.
    """
    name = f"{model.__name__.lower()}serialnumbercounter"
    class_name = f"{model.__name__}SerialNumberCounter"
    db_table = f"{model._meta.app_label.lower()}_{name}"

    meta = type(
        "Meta",
        (),
        {
            "db_table": db_table,
            "app_label": model._meta.app_label,
            "apps": model._meta.apps,
            "base_manager_name": "objects",
            "default_manager_name": "objects",
            "constraints": [
                models.UniqueConstraint(fields=["das_tenant"], name=f"{db_table}_tenant_unique"),
            ],
        },
    )

    attrs = {
        "das_tenant": models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id),
        "last_value": models.BigIntegerField(default=0),
        "tenant_id": "das_tenant_id",
        "objects": CommonTenantManager(),
        "Meta": meta,
        "__module__": model.__module__,
    }

    return type(class_name, (TenantModelMixin, UUIDModel), attrs)
