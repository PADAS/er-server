import uuid

from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantModelMixin
from oauth2_provider.models import (
    AbstractAccessToken,
    AbstractApplication,
    AbstractGrant,
    AbstractIDToken,
    AbstractRefreshToken,
)

from django.db import models

from core.models import DASTenant
from utils.migrations.columns import default_tenant_id


class DASAccessToken(TenantModelMixin, AbstractAccessToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_refresh_token = models.OneToOneField(
        # unique=True implied by the OneToOneField
        to="DASRefreshToken",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refreshed_access_token",
    )
    id_token = models.OneToOneField(
        to="DASIDToken",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="access_token",
    )
    application = TenantForeignKey(
        to="DASApplication",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "DAS Access Token"
        verbose_name_plural = "DAS Access Tokens"


class DASApplication(TenantModelMixin, AbstractApplication):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "DAS Application"
        verbose_name_plural = "DAS Applications"


class DASGrant(TenantModelMixin, AbstractGrant):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    application = TenantForeignKey(to="DASApplication", on_delete=models.CASCADE)
    das_tenant = TenantForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
    )

    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "DAS Grant"
        verbose_name_plural = "DAS Grants"


class DASIDToken(TenantModelMixin, AbstractIDToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    application = TenantForeignKey(
        to="DASApplication",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "DAS ID Token"
        verbose_name_plural = "DAS ID Tokens"


class DASRefreshToken(TenantModelMixin, AbstractRefreshToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    application = TenantForeignKey(to="DASApplication", on_delete=models.CASCADE)

    access_token = models.OneToOneField(
        to="DASAccessToken",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refresh_token",
    )
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "DAS Refresh Token"
        verbose_name_plural = "DAS Refresh Tokens"
