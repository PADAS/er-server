import hashlib
import logging
import time
import uuid
from random import uniform

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, connection, models, transaction
from django.db.models import BigIntegerField, Subquery, Value
from django.db.models.functions import Coalesce

from mapping.models import TileLayer


class FailedToSetSerialNumberError(Exception):
    """
    Exception raised when a serial number cannot be set.
    """


class TileLayersMixin:
    TOKENS = {"Mapbox Satellite Map": settings.MAPBOX_TOKEN}

    def _get_tile_layers(self):
        layers = []
        for configuration in TileLayer.objects.values("attributes"):
            attributes = dict(configuration["attributes"] or {})
            title = attributes.get("title") or ""
            attributes["title"] = title
            if title in self.TOKENS:
                url = attributes.get("url") or ""
                attributes["url"] = self._get_url(title, url)
            layers.append({"attributes": attributes})
        return layers

    def _get_url(self, title: str, url: str) -> str:
        token = self.TOKENS[title]
        return f"{url}?access_token={token}"


def _serial_number_lock_key(tenant_id: uuid.UUID | str, model_class: type[models.Model]) -> int:
    """Derive a stable signed int64 advisory-lock key from ``(tenant, model)``.

    ``tenant_id`` may be a ``uuid.UUID`` or ``str`` pre-save depending on how
    the caller assigned it; both must produce the same key so workers agree on
    the lock.
    """
    tenant_uuid = uuid.UUID(str(tenant_id))
    content_type_id = ContentType.objects.get_for_model(model_class).id
    return int.from_bytes(
        hashlib.blake2b(
            tenant_uuid.bytes + content_type_id.to_bytes(4, "big"),
            digest_size=8,
        ).digest(),
        byteorder="big",
        signed=True,
    )


class SerialNumberModelMixin:
    """
    Adds an incremental serial number on inserts.
    The model must have a field of a numeric type.
    The default field name is serial_number but it can be overriden by setting
    'serial_number_field = "your_field_name"' in the model.
    """

    def save(self, *args, **kwargs):
        """
        Save method with transaction-aware serial number generation.

        This method handles IntegrityError exceptions that can occur during
        concurrent serial number generation by using a transaction-aware
        retry mechanism that properly handles transaction rollbacks.
        """
        if self._state.adding:
            return self._save_with_serial_number(*args, **kwargs)
        else:
            return super().save(*args, **kwargs)

    def _save_with_serial_number(self, *args, **kwargs):
        """
        Save method for new objects with automatic serial number generation.

        Serializes concurrent mixin writers for a given ``(tenant, model)``
        with ``pg_advisory_xact_lock`` so the embedded ``MAX+1`` subquery
        cannot race against itself. The retry loop remains as a safety net
        for non-mixin writers (bulk_create, raw SQL) that can still commit
        between our subquery and INSERT.
        """
        serial_number_field_name = self._get_serial_number_field_name()
        tenant_id = getattr(self, "das_tenant_id", None)

        if tenant_id is None:
            raise FailedToSetSerialNumberError(
                f"Cannot generate serial number without a tenant for {self.__class__.__name__}"
            )

        max_retries = 40
        retries = 0

        while retries < max_retries:
            try:
                with transaction.atomic():
                    lock_key = _serial_number_lock_key(tenant_id, self.__class__)
                    # 8-byte digest -> pg_advisory_xact_lock bigint keyspace.
                    # blake2b (not hash()) because PYTHONHASHSEED randomizes
                    # hash() per-process, which would break cross-worker lock
                    # agreement.
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])

                    setattr(
                        self,
                        serial_number_field_name,
                        Coalesce(
                            Subquery(
                                self.__class__.objects.filter(
                                    das_tenant_id=tenant_id,
                                    **{f"{serial_number_field_name}__isnull": False},
                                )
                                .order_by(f"-{serial_number_field_name}")
                                .values(serial_number_field_name)[:1],
                                output_field=BigIntegerField(),
                            ),
                            Value(0),
                        )
                        + Value(1),
                    )

                    result = super().save(*args, **kwargs)
                self.refresh_from_db()
                return result

            except IntegrityError as exc:
                retries += 1
                if retries < max_retries:
                    # Log the retry attempt
                    logger = logging.getLogger(self.__class__.__module__)
                    logger.warning(
                        "Caught IntegrityError during serial number generation: %s. " "Retrying %s (attempt %d/%d).",
                        str(exc),
                        self.__class__.__name__,
                        retries,
                        max_retries,
                    )
                    # Small random delay to reduce collision probability
                    time.sleep(uniform(0.1, 0.6))
                    # Reset the serial number field to None so it gets regenerated
                    setattr(self, serial_number_field_name, None)
                else:
                    # Max retries exceeded, raise the exception
                    raise FailedToSetSerialNumberError(
                        f"Failed to set serial number after {max_retries} retries: {exc}"
                    )

    def _get_serial_number_field_name(self):
        if hasattr(self, "serial_number_field"):
            return self.serial_number_field
        if hasattr(self, "serial_number"):
            return "serial_number"
        raise AttributeError(
            f"Serial number field not found. Please either add a serial_number field "
            f"or set serial_number_field in {self.__class__.__name__}"
        )
