from django.conf import settings
from django.db import transaction

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
    name with ``serial_number_field = "your_field_name"``) and a ``das_tenant``
    foreign key.

    Allocation goes through ``core.SerialNumberCounter``: the counter row for
    ``(tenant, model)`` is locked with ``SELECT ... FOR UPDATE`` and incremented
    inside the same transaction as the insert. The row-level lock serializes
    concurrent inserts on the same tenant+model, so the unique constraint on
    ``(das_tenant, serial_number)`` cannot collide and no retry loop is needed.
    """

    def save(self, *args, **kwargs):
        if self._state.adding:
            return self._save_with_serial_number(*args, **kwargs)
        return super().save(*args, **kwargs)

    def _save_with_serial_number(self, *args, **kwargs):
        serial_number_field_name = self._get_serial_number_field_name()
        model_label = f"{self._meta.app_label}.{self.__class__.__name__}"
        tenant_id = getattr(self, "das_tenant_id", None)

        if tenant_id is None:
            raise FailedToSetSerialNumberError(
                f"Cannot generate serial number without a tenant for {self.__class__.__name__}"
            )

        # transaction.atomic() acts as a savepoint when nested inside an outer
        # transaction (e.g. PatrolsView.post) and a real transaction otherwise
        # (e.g. Celery tasks). Either way, the row lock taken below is held for
        # the duration of the insert, so no other writer can grab the same value.
        with transaction.atomic():
            next_value = self._get_next_serial_number(tenant_id, model_label)
            setattr(self, serial_number_field_name, next_value)
            result = super().save(*args, **kwargs)

        self.refresh_from_db()
        return result

    def _get_next_serial_number(self, tenant_id, model_label):
        from core.models import SerialNumberCounter

        # First-ever insert for a (tenant, model) pair: get_or_create uses
        # INSERT ... ON CONFLICT on Postgres, so concurrent first-inserts are
        # safe — one wins and the others fall through to the SELECT.
        counter, _ = SerialNumberCounter.objects.get_or_create(
            das_tenant_id=tenant_id,
            model_name=model_label,
            defaults={"last_value": 0},
        )

        counter = SerialNumberCounter.objects.select_for_update().get(pk=counter.pk)
        counter.last_value += 1
        counter.save(update_fields=["last_value"])

        return counter.last_value

    def _get_serial_number_field_name(self):
        if hasattr(self, "serial_number_field"):
            return self.serial_number_field
        if hasattr(self, "serial_number"):
            return "serial_number"
        raise AttributeError(
            f"Serial number field not found. Please either add a serial_number field "
            f"or set serial_number_field in {self.__class__.__name__}"
        )
