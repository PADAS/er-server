import uuid

from oauth2_provider.models import (
    AbstractAccessToken,
    AbstractApplication,
    AbstractGrant,
    AbstractIDToken,
    AbstractRefreshToken,
)

from django.db import models


class DASAccessToken(AbstractAccessToken):
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
    application = models.ForeignKey(
        to="DASApplication",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "DAS Access Token"
        verbose_name_plural = "DAS Access Tokens"


class DASApplication(AbstractApplication):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    class Meta:
        verbose_name = "DAS Application"
        verbose_name_plural = "DAS Applications"


class DASGrant(AbstractGrant):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    application = models.ForeignKey(to="DASApplication", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "DAS Grant"
        verbose_name_plural = "DAS Grants"


class DASIDToken(AbstractIDToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    application = models.ForeignKey(
        to="DASApplication",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "DAS ID Token"
        verbose_name_plural = "DAS ID Tokens"


class DASRefreshToken(AbstractRefreshToken):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    application = models.ForeignKey(to="DASApplication", on_delete=models.CASCADE)

    access_token = models.OneToOneField(
        to="DASAccessToken",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refresh_token",
    )

    class Meta:
        verbose_name = "DAS Refresh Token"
        verbose_name_plural = "DAS Refresh Tokens"
