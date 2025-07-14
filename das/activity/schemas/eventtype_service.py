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

from django.db.models import QuerySet
from rest_framework.request import Request  # type: ignore

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
class RenderOptions:
    """
    Wrappes all schema rendering options, for now only one: `pre_render`, will help to keep the contract
    between the API and the internal implementation stable.
    """

    pre_render: bool = False  # dereference $ref & bundle defs


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

    def __init__(self, request: Optional[Request] = None):
        self.request = request
        self._renderer: Optional[SchemaRenderer] = None

    def render_schema(self, event_type: EventType, options: Optional[RenderOptions] = None) -> SchemaResult:
        """Parses the raw schema field and (optionally) dereferences $refs using `SchemaRenderer` implementation.

        Always returns a `SchemaResult`, even when errors occur we try to return the schema gathered so far
        so that clients can still inspect or use it (e.g. when the error is in a non-required field).
        """
        options = options or RenderOptions()
        schema, errors = self._parse_and_render(event_type, options)
        return SchemaResult(event_type_value=event_type.value, schema=schema, errors=errors)

    def bulk_render_schemas(
        self, queryset: QuerySet[EventType], options: Optional[RenderOptions] = None
    ) -> List[SchemaResult]:
        """Convenience wrapper for list endpoint."""
        options = options or RenderOptions()
        return [self.render_schema(et, options=options) for et in queryset]

    def _get_renderer(self) -> SchemaRenderer:
        if self._renderer is None:
            registry = build_dynamic_schemas_registry(self.request) if self.request else None
            self._renderer = SchemaRenderer(registry) if registry else SchemaRenderer(None)
        return self._renderer

    def _parse_and_render(
        self,
        event_type: EventType,
        options: RenderOptions,
    ) -> tuple[Optional[dict], List[SchemaError]]:

        # --------------------------------------------------------------
        # basic checks
        # --------------------------------------------------------------
        raw_schema = event_type.schema
        if not raw_schema:
            return None, [
                SchemaError(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.MISSING_SCHEMA_STRUCTURE,
                    message="No schema defined for this event type.",
                    context={"event_type": event_type.value},
                    hints=[
                        ErrorHint(
                            message="Check that the schema is defined in the event type.",
                            action_type="fix",
                        )
                    ],
                )
            ]

        try:
            parsed_schema = json.loads(raw_schema)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in schema for %s: %s", event_type.value, exc)
            return None, [
                SchemaError(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.SCHEMA_PARSING_ERROR,
                    message="Schema contains invalid JSON.",
                    context={"event_type": event_type.value},
                    cause=exc,
                    hints=[
                        ErrorHint(
                            message="Check that the schema is valid JSON.",
                            action_type="fix",
                        )
                    ],
                )
            ]

        if "json" not in parsed_schema:
            return parsed_schema, [
                SchemaError(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.MISSING_SCHEMA_STRUCTURE,
                    message="Schema missing 'json' top-level key.",
                    context={"event_type": event_type.value},
                    hints=[
                        ErrorHint(
                            message="Check that the schema has a 'json' top-level key.",
                            action_type="fix",
                        )
                    ],
                )
            ]

        # --------------------------------------------------------------
        # optional dereference
        # --------------------------------------------------------------
        if not options.pre_render:
            return parsed_schema, []

        renderer = self._get_renderer()
        try:
            # TODO: capture / propagate errors from dereference_schema proces
            parsed_schema["json"] = renderer.dereference_schema(parsed_schema["json"])
            return parsed_schema, []
        except Exception as exc:  # pylint: disable=broad-except
            schema_error = SchemaError(
                category=ErrorCategory.RENDERING,
                code=ErrorCode.SCHEMA_RENDERING_ERROR,
                message="Error rendering schema.",
                context={"event_type": event_type.value},
                cause=exc,
                hints=[
                    ErrorHint(
                        message="Check that the schema is valid JSON.",
                        action_type="fix",
                    )
                ],
            )
            return parsed_schema, [schema_error]
