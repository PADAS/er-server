from django.conf import settings
from django.db.models import BigIntegerField, Subquery, Value
from django.db.models.functions import Coalesce

from mapping.models import TileLayer


class TileLayersMixin:
    TOKENS = {"Mapbox Satellite Map": settings.MAPBOX_TOKEN}

    def _get_tile_layers(self):
        layers = []
        for configuration in TileLayer.objects.values("attributes"):
            attributes = configuration["attributes"]
            title = attributes.get("title")
            if title in self.TOKENS:
                url = attributes["url"]
                configuration["attributes"]["url"] = self._get_url(title, url)
            layers.append(configuration)
        return layers

    def _get_url(self, title: str, url: str) -> str:
        token = self.TOKENS[title]
        return f"{url}?access_token={token}"


class SerialNumberModelMixin:
    """
    Adds an incremental serial number on inserts.
    The model must have a field of a numeric type.
    The default field name is serial_number but it can be overriden by setting
    'serial_number_field = "your_field_name"' in the model.
    """

    def save(self, *args, **kwargs):
        if self._state.adding:
            serial_number_field_name = self._get_serial_number_field_name()
            setattr(
                self,
                serial_number_field_name,
                Coalesce(
                    Subquery(
                        self.__class__.objects.filter(serial_number__isnull=False)
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

    def _get_serial_number_field_name(self):
        if hasattr(self, "serial_number_field"):
            return self.serial_number_field
        if hasattr(self, "serial_number"):
            return "serial_number"
        raise AttributeError(
            f"Serial number field not found. Please either add a serial_number field or set serial_number_field in {self.__class__.__name__}"
        )
