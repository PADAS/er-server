import logging
import time
from random import uniform

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max

from mapping.models import TileLayer


class FailedToSetSerialNumberError(Exception):
    """Raised when a serial number cannot be allocated for an inserted row."""


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


class SerialNumberModelMixin:
    """
    Adds a per-tenant monotonically-increasing serial number to inserts.

    The model must declare a numeric ``serial_number`` field (or override the
    name with ``serial_number_field = "your_field_name"``), a ``das_tenant``
    foreign key, and a ``serial_number_counter_model`` class attribute pointing
    at a per-model counter table built via
    :func:`core.models.create_serial_number_counter_model`.

    Allocation locks the counter row for the tenant with ``SELECT ... FOR
    UPDATE`` and reconciles ``last_value`` against
    ``MAX(serial_number)`` on every call, so the counter self-heals when rows
    are inserted outside this mixin (bulk_create, raw SQL) or when the counter
    table is brand-new with no seed row. The retry loop is a safety net for
    the narrow window in which a non-mixin writer commits between our
    ``MAX()`` and our ``INSERT``.
    """

    def save(self, *args, **kwargs):
        if self._state.adding:
            return self._save_with_serial_number(*args, **kwargs)
        return super().save(*args, **kwargs)

    def _save_with_serial_number(self, *args, **kwargs):
        serial_number_field_name = self._get_serial_number_field_name()
        Counter = self.serial_number_counter_model
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
                    counter, _ = Counter.objects.get_or_create(das_tenant_id=tenant_id, defaults={"last_value": 0})
                    # Row lock serializes concurrent mixin writers for this
                    # tenant, so no two of them compute the same next_value.
                    counter = Counter.objects.select_for_update().get(pk=counter.pk)
                    # MAX() reconciles against rows inserted outside the mixin
                    # (bulk_create, raw SQL) that would leave last_value
                    # trailing the true maximum. Cheap: backwards index scan
                    # on the existing (das_tenant, serial_number) unique index.
                    true_max = (
                        self.__class__.objects.filter(
                            das_tenant_id=tenant_id,
                            **{f"{serial_number_field_name}__isnull": False},
                        ).aggregate(m=Max(serial_number_field_name))["m"]
                        or 0
                    )
                    next_value = max(counter.last_value, true_max) + 1
                    setattr(self, serial_number_field_name, next_value)
                    result = super().save(*args, **kwargs)
                    counter.last_value = next_value
                    counter.save(update_fields=["last_value"])
                self.refresh_from_db()
                return result

            except IntegrityError as exc:
                retries += 1
                if retries < max_retries:
                    logger = logging.getLogger(self.__class__.__module__)
                    logger.warning(
                        "Caught IntegrityError during serial number generation: %s. " "Retrying %s (attempt %d/%d).",
                        str(exc),
                        self.__class__.__name__,
                        retries,
                        max_retries,
                    )
                    time.sleep(uniform(0.1, 0.6))
                    setattr(self, serial_number_field_name, None)
                else:
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
