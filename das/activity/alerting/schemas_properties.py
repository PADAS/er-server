"""Alert-specific schema processing service for EventTypes.

Provides clean separation between V1 and V2 EventType schema processing
for alert condition generation, following the pattern established by
EventTypeSchemaService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from django.contrib.auth.models import User
from rest_framework.request import Request as DRFRequest

from activity.models import EventType
from activity.schemas.errors import SchemaError
from activity.schemas.eventtype_service import EventTypeSchemaService
from core.utils import NonHttpRequest
from utils import schema_utils

logger = logging.getLogger(__name__)


@dataclass
class SchemaPropertiesResult:
    """Standardized result for alert schema processing."""

    event_type_value: str
    properties: Dict[str, dict]  # Flattened properties ready for alert processing
    choice_options_map: Dict[str, dict]  # Field name -> resolved choice options
    version: EventType.VersionChoices
    status: str  # 'success', 'partial', 'failure'
    errors: List[SchemaError] = field(default_factory=list)


class AlertSchemaAdapter:
    """
    Adapter for EventType v1 and v2 schemas specifically for alert conditions.
    """

    def __init__(self):
        self.v2_service = EventTypeSchemaService()

    def get_alert_properties(self, event_type: EventType, request: DRFRequest = None) -> SchemaPropertiesResult:
        """Main entry point - detects version and routes appropriately.

        Args:
            event_type: The EventType to process
            request: Optional DRF request. If None, a synthetic superuser request is created
                    to ensure all schema options are available (used for alert rule evaluation)
        """
        # Create superuser request if none provided (for alert rule evaluation)
        if request is None:
            request = self._create_superuser_request()

        if event_type.version == EventType.VersionChoices.VERSION_1:
            return self._process_v1_schema(event_type)
        else:
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

            return SchemaPropertiesResult(
                event_type_value=event_type.value,
                properties=properties,
                choice_options_map=choice_options_map,
                version=event_type.version,
                status="success",
            )

        except Exception as e:  # pylint: disable=broad-except
            logger.error("V1 schema processing failed for %s: %s", event_type.value, e)
            return SchemaPropertiesResult(
                event_type_value=event_type.value,
                properties={},
                choice_options_map={},
                version=event_type.version,
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
            version=event_type.version,
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
        """Extract choice options from V2 field properties with $ref resolution."""
        try:
            # Look for resolved choice options in anyOf structure
            any_of = field_properties.get("anyOf", [])
            choice_options = {}

            for option in any_of:
                if "oneOf" in option:
                    choice_options.update({o.get("const"): o.get("title") for o in option["oneOf"]})
                elif "const" in option:
                    choice_options.update({option.get("const"): option.get("title")})

            return choice_options

        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Failed to extract V2 choice options: %s", e)
            return {}

    def resolve_choice_options(self, field_properties: dict, event_type_version: str) -> dict:
        """Version-aware choice field resolution."""
        if event_type_version == EventType.VersionChoices.VERSION_2:
            return self._extract_v2_choice_options(field_properties)
        else:
            return self._extract_v1_choice_options(field_properties)
