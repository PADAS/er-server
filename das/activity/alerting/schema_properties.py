"""
Alert-specific schema processing service for EventTypes.

Provides clean separation between V1 and V2 EventType schema processing for alert condition generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.contrib.auth.models import User
from rest_framework.request import Request as DRFRequest

from activity.models import EventType
from activity.schemas.errors import SchemaError
from activity.schemas.eventtype_service import EventTypeSchemaService
from core.utils import NonHttpRequest
from schemas.view_mixins import ENUM_EXTRA_KEY
from utils import schema_utils

logger = logging.getLogger(__name__)


@dataclass
class SchemaPropertiesResult:
    """Standardized result for alert schema processing."""

    event_type_value: str
    properties: dict[str, dict]  # Flattened properties ready for alert processing
    choice_options_map: dict[str, dict]  # Field name -> resolved choice options
    version: EventType.VersionChoices
    status: str  # 'success', 'partial', 'failure'
    errors: list[SchemaError] = field(default_factory=list)


class AlertingSchemaPropertiesAdapter:
    """
    Properties extractor for EventType schemas (v1 and v2), specifically for alert conditions.
    """

    def __init__(self):
        self.v2_service = EventTypeSchemaService()

    def get_alert_properties(self, event_type: EventType, request: DRFRequest | None = None) -> SchemaPropertiesResult:
        """Main entry point - detects version and routes appropriately.

        Args:
            event_type: The EventType to process
            request: Optional DRF request. If None, a synthetic superuser request is created
                    to ensure all schema options are available (used for alert rule evaluation)
        """
        if event_type.version == EventType.VersionChoices.VERSION_1:
            return self._process_v1_schema(event_type)

        # Create superuser request if none provided (for alert rule evaluation)
        if request is None:
            request = self._create_superuser_request()
        return self._process_v2_schema(event_type, request)

    def _create_superuser_request(self) -> DRFRequest:
        """Create a synthetic superuser request for alert rule evaluation.

        This ensures that V2 schema processing has access to all possible
        options and data, which is needed for comprehensive alert rule matching.
        """
        django_request = NonHttpRequest()
        django_request.method = "GET"
        django_request.user = User(is_superuser=True)
        return DRFRequest(django_request)

    def _process_v1_schema(self, event_type: EventType) -> SchemaPropertiesResult:
        """V1-specific processing using legacy utils."""
        try:
            rendered_schema = schema_utils.get_rendered_schema(event_type.schema)
            properties = rendered_schema.get("properties", {})

            choice_options_map = {}
            for field_name, field_props in properties.items():
                if "enumNames" in field_props:
                    choice_options_map[field_name] = self._extract_v1_choice_options(field_props)
                elif field_props.get("type") == "array":
                    items = field_props.get("items", {})
                    if "enumNames" in items:
                        choice_options_map[field_name] = self._extract_v1_choice_options(items)

            return SchemaPropertiesResult(
                event_type_value=event_type.value,
                properties=properties,
                choice_options_map=choice_options_map,
                version=EventType.VersionChoices.VERSION_1,
                status="success",
            )

        except Exception as e:  # pylint: disable=broad-except
            logger.error("V1 schema processing failed for %s: %s", event_type.value, e)
            return SchemaPropertiesResult(
                event_type_value=event_type.value,
                properties={},
                choice_options_map={},
                version=EventType.VersionChoices.VERSION_1,
                status="failure",
                errors=[
                    SchemaError(
                        category="validation",
                        code="v1_processing_error",
                        message=f"V1 schema processing failed: {str(e)}",
                    )
                ],
            )

    def _process_v2_schema(self, event_type: EventType, request: DRFRequest) -> SchemaPropertiesResult:
        """V2-specific processing using EventTypeSchemaService."""
        # Delegate to existing V2 service
        schema_result = self.v2_service.get_rendered_schema(event_type, request)

        # Extract properties from V2 nested structure
        properties = {}
        choice_options_map = {}

        if schema_result.schema and "json" in schema_result.schema:
            json_schema = schema_result.schema["json"]
            properties = json_schema.get("properties", {})

            for field_name, field_props in properties.items():
                choice_options = self._extract_v2_choice_options(field_props)
                if choice_options:
                    choice_options_map[field_name] = choice_options

        return SchemaPropertiesResult(
            event_type_value=event_type.value,
            properties=properties,
            choice_options_map=choice_options_map,
            version=EventType.VersionChoices.VERSION_2,
            status=schema_result.status.value,
            errors=schema_result.errors,
        )

    def _extract_v1_choice_options(self, field_properties: dict) -> dict:
        """Extract choice options from V1 field properties."""
        enum_names = field_properties.get("enumNames", {})
        if isinstance(enum_names, dict):
            return enum_names
        else:
            logger.warning("V1 enumNames is not a dict: %s", enum_names)
            return {}

    def _extract_v2_choice_options(self, field_properties: dict) -> dict:
        """Extract choice options from V2 field properties with $ref resolution.

        Handles single-select and multi-select (``type=array``), including ``enum`` + ``x-enumExtra``
        (``display`` / ``description``) and legacy ``anyOf`` / ``oneOf`` shapes.
        """
        try:
            # Multi-select: type=array with choices inside items
            if field_properties.get("type") == "array":
                source = field_properties.get("items", {})
            else:
                source = field_properties

            choice_options = self._choice_options_from_enum_extra(source)
            if choice_options:
                return choice_options

            any_of = source.get("anyOf", [])
            choice_options = {}

            for option in any_of:
                nested = self._choice_options_from_enum_extra(option)
                if nested:
                    choice_options.update(nested)
                elif "oneOf" in option:
                    choice_options.update({o.get("const"): o.get("title") for o in option["oneOf"]})
                elif "const" in option:
                    choice_options.update({option.get("const"): option.get("title")})

            return choice_options

        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Failed to extract V2 choice options: %s", e)
            return {}

    @staticmethod
    def _choice_options_from_enum_extra(source: dict) -> dict:
        """Build enum value -> display label map from ``enum`` + ``x-enumExtra``."""
        extra = source.get(ENUM_EXTRA_KEY)
        if "enum" not in source or not isinstance(extra, dict):
            return {}
        out = {}
        for val in source["enum"]:
            meta = extra.get(val)
            if meta is None:
                meta = extra.get(str(val))
            if isinstance(meta, dict) and meta.get("display") is not None:
                out[val] = meta["display"]
            else:
                out[val] = str(val)
        return out

    def resolve_choice_options(self, field_properties: dict, event_type_version: str) -> dict:
        """Version-aware choice field resolution."""
        if event_type_version == EventType.VersionChoices.VERSION_2:
            return self._extract_v2_choice_options(field_properties)
        else:
            return self._extract_v1_choice_options(field_properties)
