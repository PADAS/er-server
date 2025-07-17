"""High-level service for EventType JSON schema operations.

Keeps *all* business logic (parse, render, bulk aggregation) away from
ViewSets so the API layer can remain thin.  The service is entirely
framework-agnostic (no DRF) except for requiring the Django ``Request``
object when dereferencing dynamic $ref URLs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from rest_framework.request import Request as DRFRequest

from activity.models import EventType
from activity.schemas.errors import ErrorCategory, ErrorCode, ErrorHint, SchemaError
from activity.schemas.schema_rendering import SchemaRenderer
from activity.schemas.schema_retrieving import build_dynamic_schemas_registry

logger = logging.getLogger(__name__)


class StrEnum(str, Enum):
    """Enum that can be used as a string."""


class RenderStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"  # some errors occurred, but schema is still usable
    FAILURE = "failure"  # no schema, schema is not processable


class RenderErrors(StrEnum):
    NO_SCHEMA_DEFINED = "no_schema_defined"
    INVALID_JSON = "invalid_json"
    NO_JSON_KEY = "no_json_key"
    INVALID_SCHEMA = "invalid_schema"
    SCHEMA_RENDERING_ERROR = "rendering_error"


@dataclass
class SchemaResult:
    """
    API representation of a rendered schema, holds structured errors so that multiple independent failures
    (e.g. multiple `$ref`s) can be returned in one response!
    """

    event_type_value: str
    schema: Optional[dict] = None
    errors: List[SchemaError] = field(default_factory=list)

    @property
    def status(self) -> RenderStatus:
        if any(err.category == ErrorCategory.VALIDATION for err in self.errors):
            return RenderStatus.FAILURE
        if len(self.errors) > 0:
            return RenderStatus.PARTIAL
        return RenderStatus.SUCCESS

    def to_api_dict(self) -> dict:
        api_dict = {
            "value": self.event_type_value,
            "status": self.status,
            "schema": self.schema,  # may be None if parsing failed early
        }
        if self.status != RenderStatus.SUCCESS:
            api_dict["errors"] = [err.to_dict() for err in self.errors]
        return api_dict


class EventTypeSchemaService:
    """Service encapsulating all schema operations for ``EventTypes``."""

    def __init__(self):
        self.renderer: Optional[SchemaRenderer] = None

    def get_raw_schema(self, event_type: EventType) -> SchemaResult:
        """
        Returns a "raw schema" wrapped in a `SchemaResult`, ready to be returned as-is to the API layer.
        It parses performs some basic checks over the structure of the schema, note that it doesn't perform any
        dereferencing.
        """
        schema, errors = self.parse_schema(event_type.schema)
        return SchemaResult(event_type_value=event_type.value, schema=schema, errors=errors)

    def get_rendered_schema(self, event_type: EventType, request: DRFRequest) -> SchemaResult:
        """
        Returns a "rendered schema" wrapped in a `SchemaResult`, ready to be returned as-is to the API layer.

        Always returns a `SchemaResult`, even when errors occur we try to return the schema gathered so far
        so that clients can still inspect or use it (e.g. when the error is in a non-required field).
        """
        schema, errors = self.parse_schema(event_type.schema)
        if not errors:
            schema, errors = self.render_schema(schema, request)
        return SchemaResult(event_type_value=event_type.value, schema=schema, errors=errors)

    def parse_schema(self, raw_schema: str) -> tuple[Optional[dict], List[SchemaError]]:
        """
        Parses the raw schema field, returns a tuple of the parsed schema and a list of errors.
        """
        raw_schema = raw_schema.strip()
        parsed_schema = None

        if not raw_schema:
            return None, [
                SchemaError(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.NO_SCHEMA_DEFINED,
                    message="No schema defined in the event type.",
                    hints=[
                        ErrorHint(
                            message="Update/define an event type schema, via the API, UI, or the admin interface.",
                            action_type="fix",
                        )
                    ],
                )
            ]

        try:
            parsed_schema = json.loads(raw_schema)
        except json.JSONDecodeError as exc:
            return None, [
                SchemaError(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.SCHEMA_PARSING_ERROR,
                    message="Schema contains invalid JSON.",
                    hints=[
                        ErrorHint(
                            message="Update/define an event type schema, via the API, UI, or the admin interface.",
                            action_type="fix",
                        )
                    ],
                    cause=exc,
                )
            ]

        if "json" not in parsed_schema or "ui" not in parsed_schema:
            return parsed_schema, [
                SchemaError(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.SCHEMA_STRUCTURE_ERROR,
                    message="Schema missing 'json' or 'ui' top-level key.",
                    hints=[
                        ErrorHint(
                            message="Update/define an event type schema, via the API, UI, or the admin interface.",
                            action_type="fix",
                        )
                    ],
                )
            ]
        return parsed_schema, []

    def get_renderer(self, request: DRFRequest) -> SchemaRenderer:
        # Temporal implementation while build_dynamic_schemas_registry is not ready
        if self.renderer is None:
            registry = build_dynamic_schemas_registry(request)
            self.renderer = SchemaRenderer(registry)
        return self.renderer

    def render_schema(self, parsed_schema: dict, request: DRFRequest) -> tuple[dict, List[SchemaError]]:
        """
        Renders a parsed schema. Always returns tuple of (schema, errors).

        At this point we expect a structure valid schema, so we can just render it.
        """

        renderer = self.get_renderer(request)
        try:
            parsed_schema["json"] = renderer.dereference_schema(parsed_schema["json"])
            return parsed_schema, []
        except Exception as exc:  # pylint: disable=broad-except
            # GENERIC ERROR, dereference_schema will collect and handle errors, in progress...
            schema_error = SchemaError(
                category=ErrorCategory.RENDERING,
                code=ErrorCode.SCHEMA_RENDERING_ERROR,
                message="Error rendering schema.",
                hints=[],
                cause=exc,
            )
            return parsed_schema, [schema_error]
