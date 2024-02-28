from django_multitenant.mixins import TenantModelMixin

from django.db import models

from core.models import DASTenant, UUIDModel
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager


class TenantThroughModel(TenantModelMixin, UUIDModel):
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="%(app_label)s_%(class)s",
    )

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        abstract = True
        base_manager_name = "objects"
        default_manager_name = "objects"
