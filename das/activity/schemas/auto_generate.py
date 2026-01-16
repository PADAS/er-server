"""
Auto-generate V2 EventType schemas from incoming event data.

This module provides functionality to automatically generate a V2 schema
based on the properties found in the first event posted for an EventType
that has an auto-generate marker schema.
"""

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

V2_DRAFT = "https://json-schema.org/draft/2020-12/schema"

# Regex patterns for type inference
ISO_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


class V2FieldType:
    """V2 field type constants."""

    TEXT = "TEXT"
    NUMERIC = "NUMERIC"
    BOOLEAN = "BOOLEAN"
    DATE_TIME = "DATE_TIME"
    LOCATION = "LOCATION"
    LINK = "LINK"


class V2SchemaAutoBuilder:
    """
    Builder for auto-generating V2 EventType schemas from event data.

    Given a document (dict of event properties), this builder inspects each
    property value and generates an appropriate V2 schema with both `json`
    and `ui` sections.
    """

    DEFAULT_SECTION_ID = "section-1"

    def __init__(self):
        self._fields: dict[str, dict] = {}
        self._ui_fields: dict[str, dict] = {}
        self._field_order: list[str] = []

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> dict:
        """
        Generate a V2 schema from the given document.

        Args:
            doc: A dictionary of event properties to generate schema from.

        Returns:
            A valid V2 EventType schema with `json` and `ui` sections.
        """
        builder = cls()
        for key, value in doc.items():
            builder.add_field_from_value(key, value)
        return builder.build()

    def add_field_from_value(self, key: str, value: Any) -> "V2SchemaAutoBuilder":
        """
        Add a field to the schema by inferring its type from the value.

        Args:
            key: The field name/key.
            value: The field value to infer type from.

        Returns:
            Self for method chaining.
        """
        field_type, format_hint = self._infer_type(value)

        if field_type is None:
            logger.warning(f"Unsupported type for field {key}: {type(value)}")
            return self

        title = self._generate_title(key)

        json_field = self._build_json_field(field_type, title, format_hint)
        ui_field = self._build_ui_field(field_type)

        self._fields[key] = json_field
        self._ui_fields[key] = ui_field
        self._field_order.append(key)

        return self

    def build(self) -> dict:
        """
        Build the complete V2 schema.

        Returns:
            A valid V2 EventType schema dictionary.
        """
        return {
            "json": self._build_json_schema(),
            "ui": self._build_ui_schema(),
        }

    def _infer_type(self, value: Any) -> tuple[Optional[str], Optional[str]]:
        """
        Infer the V2 field type from a Python value.

        Args:
            value: The value to infer type from.

        Returns:
            A tuple of (field_type, format_hint). Returns (None, None) if
            the value type is not supported for auto-generation.
        """
        # TODO: Add boolean field support when V2 schema spec includes boolean_field_schema.
        # Currently, V2 schemas don't have a defined boolean field type. When the spec is
        # updated, change this to return V2FieldType.BOOLEAN instead of (None, None).
        # Note: bool check must come before int check since Python's bool is a subclass of int.
        if isinstance(value, bool):
            return None, None

        if isinstance(value, (int, float)):
            return V2FieldType.NUMERIC, None

        if isinstance(value, str):
            return self._infer_string_type(value)

        if isinstance(value, dict):
            return self._infer_dict_type(value)

        return None, None

    def _infer_string_type(self, value: str) -> tuple[str, Optional[str]]:
        """
        Infer the specific string field type from a string value.

        Args:
            value: The string value to analyze.

        Returns:
            A tuple of (field_type, format_hint).
        """
        if ISO_DATETIME_PATTERN.match(value):
            return V2FieldType.DATE_TIME, "date-time"

        if ISO_DATE_PATTERN.match(value):
            return V2FieldType.DATE_TIME, "date"

        if ISO_TIME_PATTERN.match(value):
            return V2FieldType.DATE_TIME, "time"

        if URL_PATTERN.match(value):
            return V2FieldType.LINK, "uri"

        return V2FieldType.TEXT, None

    def _infer_dict_type(self, value: dict) -> tuple[Optional[str], Optional[str]]:
        """
        Infer type from a dictionary value.

        Currently only supports location objects with latitude/longitude.

        Args:
            value: The dictionary value to analyze.

        Returns:
            A tuple of (field_type, format_hint).
        """
        if self._is_location_object(value):
            return V2FieldType.LOCATION, None

        return None, None

    def _is_location_object(self, value: dict) -> bool:
        """Check if the dict represents a location with lat/lon."""
        if not isinstance(value, dict):
            return False

        has_latitude = "latitude" in value and isinstance(value["latitude"], (int, float))
        has_longitude = "longitude" in value and isinstance(value["longitude"], (int, float))

        return has_latitude and has_longitude

    @staticmethod
    def _generate_title(key: str) -> str:
        """
        Generate a human-readable title from a field key.

        Args:
            key: The field key (e.g., "animal_count", "species_name").

        Returns:
            A title-cased string (e.g., "Animal Count", "Species Name").
        """
        return " ".join(key.strip().split("_")).title()

    def _build_json_field(self, field_type: str, title: str, format_hint: Optional[str] = None) -> dict:
        """
        Build the JSON schema definition for a field.

        Args:
            field_type: The V2 field type.
            title: The field title.
            format_hint: Optional format string (e.g., "date-time", "uri").

        Returns:
            A JSON schema field definition.
        """
        if field_type == V2FieldType.BOOLEAN:
            return {
                "deprecated": False,
                "title": title,
                "type": "boolean",
            }

        if field_type == V2FieldType.NUMERIC:
            return {
                "deprecated": False,
                "title": title,
                "type": "number",
            }

        if field_type == V2FieldType.DATE_TIME:
            return {
                "deprecated": False,
                "format": format_hint or "date-time",
                "title": title,
                "type": "string",
            }

        if field_type == V2FieldType.LINK:
            return {
                "deprecated": False,
                "format": "uri",
                "title": title,
                "type": "string",
            }

        if field_type == V2FieldType.LOCATION:
            return {
                "deprecated": False,
                "properties": {
                    "latitude": {
                        "maximum": 90,
                        "minimum": -90,
                        "type": "number",
                    },
                    "longitude": {
                        "maximum": 180,
                        "minimum": -180,
                        "type": "number",
                    },
                },
                "required": ["latitude", "longitude"],
                "title": title,
                "type": "object",
                "unevaluatedProperties": False,
            }

        return {
            "default": "",
            "deprecated": False,
            "title": title,
            "type": "string",
        }

    def _build_ui_field(self, field_type: str) -> dict:
        """
        Build the UI schema definition for a field.

        Args:
            field_type: The V2 field type.

        Returns:
            A UI schema field definition.
        """
        base = {
            "conditionalDependents": [],
            "parent": self.DEFAULT_SECTION_ID,
        }

        if field_type == V2FieldType.BOOLEAN:
            return {**base, "type": "BOOLEAN"}

        if field_type == V2FieldType.NUMERIC:
            return {**base, "placeholder": "", "type": "NUMERIC"}

        if field_type == V2FieldType.DATE_TIME:
            return {**base, "type": "DATE_TIME"}

        if field_type == V2FieldType.LOCATION:
            return {**base, "type": "LOCATION"}

        if field_type == V2FieldType.LINK:
            return {**base, "placeholder": "", "type": "LINK"}

        return {**base, "inputType": "SHORT_TEXT", "placeholder": "", "type": "TEXT"}

    def _build_json_schema(self) -> dict:
        """Build the complete JSON schema section."""
        return {
            "$schema": V2_DRAFT,
            "properties": self._fields.copy(),
            "required": [],
            "type": "object",
            "unevaluatedProperties": False,
        }

    def _build_ui_schema(self) -> dict:
        """Build the complete UI schema section."""
        left_column = [{"name": key, "type": "field"} for key in self._field_order]

        return {
            "fields": self._ui_fields.copy(),
            "headers": {},
            "order": [self.DEFAULT_SECTION_ID],
            "sections": {
                self.DEFAULT_SECTION_ID: {
                    "columns": 1,
                    "conditions": [],
                    "isActive": True,
                    "label": "Auto-generated Fields",
                    "leftColumn": left_column,
                    "rightColumn": [],
                }
            },
        }


def should_auto_generate_schema(schema_string: str) -> bool:
    """
    Check if a schema (v1 or v2) is marked for auto-generation.

    This is the unified check that works for both v1 and v2 schemas.
    Both use the same `"auto-generate": true` marker at the root level.

    Args:
        schema_string: The schema as a JSON string.

    Returns:
        True if the schema has the auto-generate marker.
    """
    if not schema_string:
        return False

    try:
        schema_doc = json.loads(schema_string)
    except (json.JSONDecodeError, TypeError):
        return False

    return schema_doc.get("auto-generate", False)
