import uuid

from django_multitenant.fields import TenantForeignKey, TenantOneToOneField
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from oauth2_provider.generators import generate_client_id
from oauth2_provider.models import (
    AbstractAccessToken,
    AbstractApplication,
    AbstractGrant,
    AbstractIDToken,
    AbstractRefreshToken,
    ApplicationManager,
)

from django.conf import settings
from django.db import models
from django.db.models.constraints import UniqueConstraint

from core.models import DASTenant
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager


class DASAccessToken(TenantModelMixin, AbstractAccessToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s",
    )
    source_refresh_token = TenantOneToOneField(
        to="DASRefreshToken",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refreshed_access_token",
    )
    id_token = TenantOneToOneField(
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
    objects = CommonTenantManager()

    class Meta:
        verbose_name = "DAS Access Token"
        verbose_name_plural = "DAS Access Tokens"

        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "token"],
                name="%(app_label)s_%(class)s_unique_token_across_tenants",
            )
        ]
        indexes = [
            models.Index(fields=["das_tenant", "token"]),
        ]


class DASApplicationManager(TenantManagerMixin, ApplicationManager):
    use_in_migrations = True


class DASApplication(TenantModelMixin, AbstractApplication):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    client_id = models.CharField(max_length=100, default=generate_client_id)
    user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(app_label)s_%(class)s",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    tenant_id = "das_tenant_id"

    objects = DASApplicationManager()

    class Meta:
        verbose_name = "DAS Application"
        verbose_name_plural = "DAS Applications"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "client_id"],
                name="%(app_label)s_%(class)s_unique_client_across_tenants",
            )
        ]
        indexes = [
            models.Index(fields=["das_tenant", "client_id"]),
        ]


class DASGrant(TenantModelMixin, AbstractGrant):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
    )
    application = TenantForeignKey(to="DASApplication", on_delete=models.CASCADE)
    das_tenant = TenantForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
    )

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        verbose_name = "DAS Grant"
        verbose_name_plural = "DAS Grants"

        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "code"],
                name="%(app_label)s_%(class)s_unique_code_across_tenants",
            )
        ]
        indexes = [
            models.Index(fields=["das_tenant", "code"]),
        ]


class DASIDToken(TenantModelMixin, AbstractIDToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s",
    )
    application = TenantForeignKey(
        to="DASApplication",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        verbose_name = "DAS ID Token"
        verbose_name_plural = "DAS ID Tokens"

        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "jti"],
                name="%(app_label)s_%(class)s_unique_jti_across_tenants",
            )
        ]
        indexes = [
            models.Index(fields=["das_tenant", "jti"]),
        ]


class DASRefreshToken(TenantModelMixin, AbstractRefreshToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
    )
    application = TenantForeignKey(to="DASApplication", on_delete=models.CASCADE)

    access_token = TenantOneToOneField(
        to="DASAccessToken",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refresh_token",
    )
    das_tenant = TenantForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        verbose_name = "DAS Refresh Token"
        verbose_name_plural = "DAS Refresh Tokens"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "token"],
                name="%(app_label)s_%(class)s_unique_token_across_tenants",
            )
        ]
        indexes = [
            models.Index(fields=["das_tenant", "token"]),
        ]
