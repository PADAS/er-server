"""
Common interface for accessing both V1 and V2 event type schemas.

This module provides a unified interface that abstracts the differences between
V1 (legacy) and V2 (new) schema formats, allowing code to work with either
schema version transparently.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Protocol, Union

from rest_framework.request import Request as DRFRequest

import utils.schema_utils as schema_utils
from activity.models import EventType
from activity.schemas.eventtype_service import EventTypeSchemaService

logger = logging.getLogger(__name__)


class SchemaAdapter(Protocol):
    """Protocol defining the interface for schema adapters."""

    def get_properties(self) -> Dict[str, Any]:
        """Get the properties dictionary from the schema."""
        ...

    def get_property_order(self) -> Dict[str, int]:
        """Get the order of properties as a dictionary mapping property names to order indices."""
        ...

    def get_column_header_name(self, key: str) -> str:
        """Get the display name for a property key."""
        ...

    def get_display_value_header_for_key(self, key: str) -> str:
        """Get display value header for key using the schema."""
        ...

    def get_display_values_for_event_details(self, event_details: Dict[str, Any], event=None) -> Dict[str, Any]:
        """Get display values for event details using the schema.
        Example: for the property key we get back the "value"s and for the title of the property we get back the "display"s.
        """
        ...


class V1SchemaAdapter:
    """Adapter for V1 (legacy) schemas. A V1 schema is a string that is rendered using jinja2."""

    def __init__(self, schema: str):
        self.schema = schema
        self._renderer = schema_utils.get_schema_renderer_method()
        self._rendered_schema = self._renderer(schema)

    @property
    def rendered_schema(self):
        return self._rendered_schema

    def get_properties(self) -> Dict[str, Any]:
        """Get properties from V1 schema structure."""
        return schema_utils.get_resolved_v1v2_properties(self.rendered_schema)

    def get_property_order(self) -> Dict[str, int]:
        """Get property order from V1 schema definition."""
        return schema_utils.property_keys_order_as_dict(self.rendered_schema)

    def get_column_header_name(self, key: str) -> str:
        """Get column header name using V1 schema logic."""
        return schema_utils.get_column_header_name(self.rendered_schema, key)

    def get_display_value_header_for_key(self, key: str) -> str:
        """Get display value header for key using V1 schema logic."""
        return schema_utils.get_display_value_header_for_key(self.rendered_schema, key)

    def get_display_values_for_event_details(self, event_details: Dict[str, Any], event=None) -> Dict[str, Any]:
        """Get display values using V1 schema logic.
        V1 event_details example: {"carcassrep_species": [{'name': 'Elephant', 'value': 'elephant'}, {'name': 'Eland', 'value': 'eland'}]}
        """
        return schema_utils.get_display_values_for_event_details(event_details, self.rendered_schema, event=event)


class V2SchemaAdapter:
    """Adapter for V2 (new) schemas."""

    def __init__(self, schema: Dict[str, Any], request: Optional[DRFRequest] = None):
        self.schema = schema
        self.request = request
        self._service = EventTypeSchemaService()
        self._rendered_schema = None
        self._properties = None
        self._property_order = None

    def _ensure_rendered(self):
        """Ensure the schema is rendered and cached."""
        if self._rendered_schema is None:
            if self.request:
                result = self._service.get_rendered_schema(EventType(schema=json.dumps(self.schema)), self.request)
                self._rendered_schema = result.schema
            else:
                # Fallback to raw schema if no request available
                self._rendered_schema = self.schema

    def get_properties(self) -> Dict[str, Any]:
        """Get properties from V2 schema structure."""
        if self._properties is None:
            self._ensure_rendered()
            self._properties = schema_utils.get_resolved_v1v2_properties(self._rendered_schema)
        return self._properties

    def get_property_order(self) -> Dict[str, int]:
        """Can't use the V1 logic for V2 schemas as V2 schemas don't have the complete order in the order/sections/section structure.
        We are limited to walking the json properties structure to construct the order list.
        """
        if self._property_order is None:
            self._property_order = schema_utils.property_keys_order_as_dict(self.schema)
        return self._property_order

    def get_column_header_name(self, key: str) -> str:
        """Get column header name using V2 schema logic."""
        self._ensure_rendered()

        # First try to get from UI schema fields
        ui_schema = self.schema.get("ui", {})
        fields = ui_schema.get("fields", {})
        if key in fields:
            field_config = fields[key]
            if "title" in field_config:
                return field_config["title"]

        # Fallback to properties title
        properties = self.get_properties()
        if key in properties and "title" in properties[key]:
            return properties[key]["title"]

        # Final fallback to formatted key
        return schema_utils.format_key_for_title(key)

    def get_display_value_header_for_key(self, key: str) -> str:
        """Get display value header for key using V2 schema logic."""
        return schema_utils.get_display_value_header_for_key(self.schema, key)

    def get_display_values_for_event_details(self, event_details: Dict[str, Any], event=None) -> Dict[str, Any]:
        """Get display values using V2 schema logic.
        V2 event_details example: {"carcassrep_species": ["elephant", "eland"]}"""
        self._ensure_rendered()

        ret = {}
        properties = self.get_properties()

        for key, value in event_details.items():
            if key not in properties:
                continue

            schema_item = properties[key]
            title, extracted_value, display = self._extract_v2_value(schema_item, key, value, event=event)

            if title and extracted_value is not None:
                ret[key] = extracted_value
                ret[title] = display

        return ret

    def _extract_v2_value(self, schema_item: Dict[str, Any], key: str, value: Any, event=None) -> tuple:
        """Extract value and display from V2 schema item."""
        if isinstance(value, list):
            return self._extract_v2_list_value(schema_item, value, event=event)
        else:
            return self._extract_v2_single_value(schema_item, value)

    def _extract_v2_single_value(self, schema_item: Dict[str, Any], value: Any) -> tuple:
        """Extract value and display for a single value from V2 schema."""
        # Get the title from schema
        title = schema_item.get("title", "")

        # Handle choice fields with anyOf/oneOf structure
        if "anyOf" in schema_item:
            display = self._find_choice_display(schema_item["anyOf"], value)
            return title, value, display if display is not None else str(value)

        # Handle simple string/number values
        return title, value, str(value)

    def _extract_v2_list_value(self, schema_item: Dict[str, Any], values: List[Any], event=None) -> tuple:
        """Extract value and display for a list value from V2 schema."""
        title = schema_item.get("title", "")

        if not values:
            return title, "", ""

        # Handle choice list fields
        if "items" in schema_item:
            schema_item = schema_item["items"]

        if "anyOf" in schema_item:
            extracted_values = []
            display_values = []

            for value in values:
                display = self._find_choice_display(schema_item["anyOf"], value)
                extracted_values.append(str(value))
                display_values.append(display if display is not None else str(value))

            return title, ";".join(extracted_values), ";".join(display_values)

        # Handle simple list values
        return title, ";".join(str(v) for v in values), ";".join(str(v) for v in values)

    def _find_choice_display(self, any_of_array: List[Dict[str, Any]], value: Any) -> Optional[str]:
        """Find the display title for a choice value in V2 schema anyOf structure."""
        for choice_ref in any_of_array:
            if "$ref" in choice_ref:
                # This is a reference that should be resolved in the rendered schema
                # Look in the rendered schema's $defs
                ref_path = choice_ref["$ref"]
                if ref_path.startswith("#/$defs/"):
                    def_key = ref_path.replace("#/$defs/", "")
                    if self._rendered_schema and "$defs" in self._rendered_schema:
                        def_schema = self._rendered_schema["$defs"].get(def_key)
                        if def_schema and "oneOf" in def_schema:
                            for choice_item in def_schema["oneOf"]:
                                if choice_item.get("const") == value:
                                    return choice_item.get("title", str(value))
                continue

            if "oneOf" in choice_ref:
                # This is the resolved choice structure
                for choice_item in choice_ref["oneOf"]:
                    if choice_item.get("const") == value:
                        return choice_item.get("title", str(value))

            # Check if this is a direct choice item with const and title
            if "const" in choice_ref and "title" in choice_ref:
                if choice_ref.get("const") == value:
                    return choice_ref.get("title", str(value))

        return None


class SchemaAdapterFactory:
    """Factory for creating appropriate schema adapters."""

    @staticmethod
    def create_adapter(
        schema: Union[str, Dict[str, Any]], request: Optional[DRFRequest] = None
    ) -> Union[V1SchemaAdapter, V2SchemaAdapter]:
        """
        Create the appropriate schema adapter based on the schema structure.

        Args:
            schema: The schema as a string (JSON) or dictionary
            request: Optional DRF request for V2 schema rendering

        Returns:
            SchemaAdapter instance
        """
        if isinstance(schema, str):
            try:
                schema_dict = json.loads(schema)
                if "json" in schema_dict and "ui" in schema_dict:
                    # V2 schema structure
                    return V2SchemaAdapter(schema_dict, request)
                elif "schema" in schema_dict and "definition" in schema_dict:
                    # V1 schema structure
                    return V1SchemaAdapter(schema)
                else:
                    # Default to V2 if we can't determine
                    logger.warning("Could not determine schema version, defaulting to V2")
                    return V2SchemaAdapter(schema_dict, request)
            except json.JSONDecodeError:
                return V1SchemaAdapter(schema)

    @staticmethod
    def create_from_event_type(
        event_type: EventType, request: Optional[DRFRequest] = None
    ) -> Union[V1SchemaAdapter, V2SchemaAdapter]:
        """
        Create a schema adapter from an EventType instance.

        Args:
            event_type: The EventType instance
            request: Optional DRF request for V2 schema rendering

        Returns:
            SchemaAdapter instance
        """
        return SchemaAdapterFactory.create_adapter(event_type.schema, request)
