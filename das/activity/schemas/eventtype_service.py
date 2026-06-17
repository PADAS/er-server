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
from activity.schemas.utils import get_field_schema_from_prop_path
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


FieldT = TypeVar("FieldT", bound=UiField)


@dataclass
class Slot(Generic[FieldT]):
    """A UI field plus its place in the schema's collection hierarchy.

    ``field_id`` is the dotted ui.fields key (e.g. ``"arrests.photo"`` for a
    single-collection-nested field, ``"outer.inner.photo"`` for a field two
    collections deep, or ``"photo"`` for a flat field).  Routing is derived
    from the key by splitting on dots:

    * ``collection_path`` — the ordered list of collection names enclosing the
      field (all segments except the last).  Empty for a flat field.
    * ``collection_parent`` — the *immediate* enclosing collection (the second-
      to-last segment), or ``None`` for flat fields.  Preserved for backward
      compatibility with existing assertions on single-level fields.
    * ``data_key`` — the leaf name (last segment), used to read the field value
      from a value-container dict (always keyed by the simple leaf, not the full
      dotted id).

    Multi-level descent: ``value_containers`` iterates ``collection_path`` from
    outermost to innermost, expanding each layer's list of dicts, so for a field
    two collections deep it yields the innermost item-dicts from *both* levels.

    This logic is field-type-agnostic — the seam future field types reuse.
    """

    field: FieldT
    field_id: str

    @property
    def collection_path(self) -> list[str]:
        """Ordered list of collection names that enclose this field (outermost first).

        For ``"outer.inner.photo"`` this is ``["outer", "inner"]``.
        For ``"arrests.photo"`` this is ``["arrests"]``.
        For a flat field ``"photo"`` this is ``[]``.
        """
        segments = self.field_id.split(".")
        return segments[:-1]

    @property
    def collection_parent(self) -> str | None:
        """The immediate (innermost) enclosing collection name, or ``None`` for flat fields.

        For ``"arrests.photo"`` returns ``"arrests"``.
        For ``"outer.inner.photo"`` returns ``"inner"`` (not ``"outer.inner"``).
        For a flat field ``"photo"`` returns ``None``.
        """
        segments = self.field_id.split(".")
        if len(segments) >= 2:
            return segments[-2]
        return None

    @property
    def data_key(self) -> str:
        """The simple leaf name used to index into a value-container dict."""
        return self.field_id.rpartition(".")[2]

    def value_containers(self, data: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield each dict that directly holds this slot's field value.

        Descends through every level of the ``collection_path`` chain:

        * Flat slot (empty ``collection_path``): yields ``data`` itself.
        * Single-level (e.g. ``"arrests.photo"``): yields each ``dict`` item of
          the ``"arrests"`` list — identical to the original behaviour.
        * Multi-level (e.g. ``"outer.inner.photo"``): iterates the ``"outer"``
          list first, then for each outer item iterates its ``"inner"`` list,
          ultimately yielding all innermost ``{"photo": [...]}`` dicts.

        At every level, a missing or non-list collection and non-dict items are
        silently skipped so that partial / sparse data does not raise.

        Each yielded dict is a reference into the passed-in ``data`` structure,
        not a copy — a caller that intends to mutate ``container[data_key]``
        must pass a copy of ``data`` first (the validation caller only reads;
        the URL-rendering caller copies before substituting).
        """
        containers: list[dict[str, Any]] = [data]
        for collection_name in self.collection_path:
            next_containers: list[dict[str, Any]] = []
            for container in containers:
                items = container.get(collection_name)
                if isinstance(items, list):
                    next_containers.extend(item for item in items if isinstance(item, dict))
            containers = next_containers
        yield from containers


@dataclass
class AttachmentField:
    """1:1 model of an ATTACHMENT entry in schema["ui"]["fields"][name].

    ``min_items`` and ``max_items`` are sourced from the field's JSON schema
    definition.  The prop-path used for traversal is derived by splitting the
    slot's dotted ``field_id`` (e.g. ``"arrests.photo"`` → path
    ``["arrests", "photo"]``) via ``get_field_schema_from_prop_path``.  For a
    flat field (no dot) the path is a single-element list.  They are ``None``
    when the property is absent or the JSON definition is missing.
    """

    type: ClassVar[str] = "ATTACHMENT"  # meta-schema const; fixed discriminant, not init data
    allowable_file_types: list[FileTypeLabel]
    min_items: int | None = None
    max_items: int | None = None


AttachmentSlot: TypeAlias = Slot[AttachmentField]


def _coerce_bound(raw: Any) -> int | None:
    """Return *raw* as a non-negative int bound, or None if it is not a valid bound.

    Rejects booleans (``isinstance(True, int)`` is True), negative ints, and any
    non-int type, all of which are invalid ``minItems`` / ``maxItems`` values.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw if raw >= 0 else None


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
        """Return a mapping of field_id -> AttachmentSlot for every ATTACHMENT field.

        Walks ``self.schema["ui"]["fields"]`` and collects every field whose
        ``type`` is ``"ATTACHMENT"``.  The map key is the dotted ui.fields key
        (e.g. ``"arrests.photo"`` for a collection-nested field, ``"photo"``
        for a flat field).

        For each slot, ``collection_path``, ``collection_parent``, and
        ``data_key`` are derived from the dotted field_id:
        ``"arrests.photo"`` → ``collection_path=["arrests"]``,
        ``collection_parent="arrests"``, ``data_key="photo"``.
        ``"outer.inner.photo"`` → ``collection_path=["outer", "inner"]``,
        ``collection_parent="inner"``, ``data_key="photo"``.
        The JSON schema definition is resolved by splitting the dotted key into
        a prop-path and passing it to ``get_field_schema_from_prop_path``,
        which traverses ``array``/``object`` nesting at every level for us.

        Precondition: ``self.schema`` is not ``None``. Callers must
        gate on ``schema_result.schema`` first; the method raises
        ``ValueError`` so contract violations surface immediately
        rather than masquerading as "no attachment fields".
        This is a pure function — no DB or GCS calls.
        """
        if self.schema is None:
            raise ValueError(
                "extract_attachment_slots requires a parsed schema; " "caller must gate on schema_result.schema first."
            )

        ui_fields: dict[str, Any] = (self.schema.get("ui") or {}).get("fields") or {}
        result: dict[str, AttachmentSlot] = {}

        for field_id, ui_def in ui_fields.items():
            if not isinstance(ui_def, dict):
                raise ValueError(
                    f"ui.fields[{field_id!r}] is {type(ui_def).__name__}, expected dict; "
                    "EventTypeV2Serializer meta-schema should have rejected this on write."
                )

        for field_id, ui_def in ui_fields.items():
            if ui_def.get("type") != "ATTACHMENT":
                continue
            allowable = cast(list[FileTypeLabel], ui_def.get("allowableFileTypes") or [])

            # Resolve minItems / maxItems from the JSON schema definition.
            # Split the dotted field_id into a prop-path so
            # get_field_schema_from_prop_path can traverse collection
            # array nesting for us (e.g. "arrests.photo" → ["arrests", "photo"]).
            json_def = get_field_schema_from_prop_path(self.schema, field_id.split("."))
            min_items: int | None = None
            max_items: int | None = None
            if isinstance(json_def, dict):
                min_items = _coerce_bound(json_def.get("minItems"))
                max_items = _coerce_bound(json_def.get("maxItems"))

            result[field_id] = AttachmentSlot(
                field=AttachmentField(
                    allowable_file_types=allowable,
                    min_items=min_items,
                    max_items=max_items,
                ),
                field_id=field_id,
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
