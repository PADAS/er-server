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
from typing import (
    Any,
    ClassVar,
    Generic,
    Iterator,
    List,
    Optional,
    Protocol,
    Tuple,
    TypeAlias,
    TypeVar,
    cast,
)

from rest_framework.request import Request as DRFRequest

from activity.models import EventType
from activity.schemas.errors import ErrorCategory, ErrorCode, ErrorHint, SchemaError
from activity.schemas.schema_rendering import SchemaRenderer
from activity.schemas.schema_retrieving import build_dynamic_schemas_registry
from usercontent.utils import FileTypeLabel
from utils import StrEnum

logger = logging.getLogger(__name__)


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


class UiField(Protocol):
    """A UI field entry in schema["ui"]["fields"][name]."""

    type: ClassVar[str]  # discriminant, e.g. "ATTACHMENT" (per-impl const)
    parent: str  # raw JSON parent: a section OR collection name


FieldT = TypeVar("FieldT", bound=UiField)


@dataclass
class Slot(Generic[FieldT]):
    """A UI field plus its place in the schema's collection hierarchy.

    `field.parent` points at the enclosing section for a flat field and at the
    enclosing COLLECTION for a nested one. `parent_is_collection` records which
    case applies (decided during the schema walk, where the full set of
    COLLECTION field names is known); `collection_parent` derives the name.
    This logic is field-type-agnostic — the seam future field types reuse.
    """

    field: FieldT
    parent_is_collection: bool

    @property
    def collection_parent(self) -> str | None:
        return self.field.parent if self.parent_is_collection else None

    def value_containers(self, data: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield each dict that directly holds this slot's field value.

        For a flat slot, yields ``data`` itself. For a collection-nested slot,
        yields each ``dict`` item of the enclosing COLLECTION list, skipping a
        missing / non-list parent and any non-dict entries.

        Each yielded dict is a reference into the passed-in ``data`` structure,
        not a copy — a caller that intends to mutate ``container[field_name]``
        must pass a copy of ``data`` first (the validation caller only reads;
        the URL-rendering caller copies before substituting).
        """
        if self.collection_parent is None:
            yield data
            return
        items = data.get(self.collection_parent)
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, dict):
                yield item


@dataclass
class AttachmentField:
    """1:1 model of an ATTACHMENT entry in schema["ui"]["fields"][name]."""

    type: ClassVar[str] = "ATTACHMENT"  # meta-schema const; fixed discriminant, not init data
    parent: str  # raw JSON parent: a section OR collection name
    allowable_file_types: list[FileTypeLabel]


AttachmentSlot: TypeAlias = Slot[AttachmentField]


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

    def extract_attachment_slots(self) -> dict[str, AttachmentSlot]:
        """Return a mapping of field_name -> AttachmentSlot for every ATTACHMENT field.

        Walks ``self.schema["ui"]["fields"]`` and collects every field whose
        ``type`` is ``"ATTACHMENT"``.  For each such field,
        ``slot.collection_parent`` is the name of the enclosing COLLECTION field
        (i.e. the parent field that has ``type == "COLLECTION"``) when the
        field is nested, otherwise ``None``.

        Precondition: ``self.schema`` is not ``None``. Callers must
        gate on ``schema_result.schema`` first; the method raises
        ``ValueError`` so contract violations surface immediately
        rather than masquerading as "no attachment fields".
        This is a pure function — no DB or GCS calls.
        """
        if self.schema is None:
            raise ValueError(
                "extract_attachment_slots requires a parsed schema; "
                "caller must gate on schema_result.schema first."
            )

        ui_fields: dict[str, Any] = (self.schema.get("ui") or {}).get("fields") or {}
        result: dict[str, AttachmentSlot] = {}

        for field_name, ui_def in ui_fields.items():
            if not isinstance(ui_def, dict):
                raise ValueError(
                    f"ui.fields[{field_name!r}] is {type(ui_def).__name__}, expected dict; "
                    "EventTypeV2Serializer meta-schema should have rejected this on write."
                )

        collection_field_names: set[str] = {
            name for name, defn in ui_fields.items() if defn.get("type") == "COLLECTION"
        }

        for field_name, ui_def in ui_fields.items():
            if ui_def.get("type") != "ATTACHMENT":
                continue
            parent = ui_def.get("parent", "")
            allowable = cast(list[FileTypeLabel], ui_def.get("allowableFileTypes") or [])
            result[field_name] = AttachmentSlot(
                field=AttachmentField(parent=parent, allowable_file_types=allowable),
                parent_is_collection=parent in collection_field_names,
            )
        return result


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

        This applies a temporary postprocessing to remove `additionalProperties: false`
        and `unevaluatedProperties: false` from the root level only, enabling clients to validate
        legacy event data that may contain fields removed from the schema.
        """
        schema, errors = self.parse_schema(event_type.schema)
        if not errors:
            schema, errors = self.render_schema(schema, request)
            # Temporary: Remove strict validation properties for client-side compatibility
            self._remove_strict_validation_properties(schema)
        return SchemaResult(event_type_value=event_type.value, schema=schema, errors=errors)

    def parse_schema(self, raw_schema: str) -> Tuple[Optional[dict], List[SchemaError]]:
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

    def render_schema(self, parsed_schema: dict, request: DRFRequest) -> Tuple[dict, List[SchemaError]]:
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

    def _remove_strict_validation_properties(self, schema: dict) -> None:
        """
        Remove strict validation properties from V2 schema root (in-place mutation).

        Temporarily removes `additionalProperties: false` and `unevaluatedProperties: false`
        from the root level of the JSON schema only. This allows clients to validate event
        data that may contain legacy fields removed from the schema, while still preserving
        strict validation within nested objects (e.g., collection field items).

        This is a temporary measure until a better solution is implemented for handling
        legacy event data validation.

        Args:
            schema: The parsed V2 schema dict with "json" and "ui" keys. Mutated in place.
        """
        json_schema = schema["json"]
        # Remove strict validation properties only at root level
        json_schema.pop("additionalProperties", None)
        json_schema.pop("unevaluatedProperties", None)
