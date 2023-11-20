from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantModelMixin

from django.db import models

from core.models import TimestampedModel, UUIDModel
from core.models.core import DASTenant
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager


class SourceProviderEvent(TenantModelMixin, TimestampedModel, UUIDModel):
    source_provider = TenantForeignKey(
        "observations.SourceProvider",
        on_delete=models.CASCADE,
        related_name="events_reached_threshold",
        related_query_name="event_reached_threshold",
    )
    event = TenantForeignKey(
        "activity.Event",
        on_delete=models.CASCADE,
        related_name="sources_provider_event",
        related_query_name="source_provider_event",
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()


class SourceEvent(TenantModelMixin, TimestampedModel, UUIDModel):
    source = TenantForeignKey(
        "observations.Source",
        on_delete=models.CASCADE,
        related_name="events_reached_threshold",
        related_query_name="event_reached_threshold",
    )
    event = TenantForeignKey(
        "activity.Event",
        on_delete=models.CASCADE,
        related_name="sources_event",
        related_query_name="source_event",
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()
