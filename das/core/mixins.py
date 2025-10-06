import logging
import time
from random import uniform

from django.conf import settings
from django.db import IntegrityError
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

        Uses a retry mechanism to handle IntegrityError exceptions that can occur
        during concurrent serial number generation. This method avoids nested
        transaction.atomic() blocks to prevent TransactionManagementError.
        """
        serial_number_field_name = self._get_serial_number_field_name()
        max_retries = 40
        retries = 0
        exception = None

        while retries < max_retries:
            try:
                # Generate the serial number
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

                # Save without nested atomic block - let the caller handle transactions
                result = super().save(*args, **kwargs)
                self.refresh_from_db()
                return result

            except IntegrityError as exc:
                exception = exc
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

        # This should never be reached, but just in case
        if exception:
            raise exception

    def _get_serial_number_field_name(self):
        if hasattr(self, "serial_number_field"):
            return self.serial_number_field
        if hasattr(self, "serial_number"):
            return "serial_number"
        raise AttributeError(
            f"Serial number field not found. Please either add a serial_number field "
            f"or set serial_number_field in {self.__class__.__name__}"
        )
