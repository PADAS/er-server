"""JSON Schema fragment writers for dynamic schema ``s_format`` (``enum`` / ``oneOf``)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Generator

# JSON Schema extension: per-value metadata for ``enum`` (display, description, optional extras).
ENUM_EXTRA_KEY = "x-enumExtra"

OUTPUT_FORMAT_ENUM = "enum"
OUTPUT_FORMAT_ONE_OF = "oneOf"
OUTPUT_FORMATS = frozenset({OUTPUT_FORMAT_ENUM, OUTPUT_FORMAT_ONE_OF})

# One row produced by the view's per-item mapping: keys from ``get_fields_map``
# (``value``, ``label``, optional ``description``, plus any ``x_<name>`` extras).
MappedItem = dict[str, Any]

SchemaFragmentSerializer = Callable[[dict[str, Any], list[MappedItem]], None]


def serialize_enum_fragment(schema: dict[str, Any], mapped_items: list[MappedItem]) -> None:
    """Write ``enum`` + ``x-enumExtra`` from mapped items (preserves order).

    Each ``value`` is keyed into ``x-enumExtra`` as-is, so the lookup key in ``x-enumExtra``
    is the same value present in ``enum``. JSON serialization will coerce non-string keys
    per the JSON spec when the schema is rendered.
    """
    enum_extra: dict[Any, Any] = {}
    enum_values: list[Any] = []
    for mi in mapped_items:
        value = mi["value"]
        entry: dict[str, Any] = {"display": mi["label"]}
        for key, val in mi.items():
            if key in ("value", "label"):
                continue
            if key == "description" and val is None:
                continue
            entry[key] = val
        enum_values.append(value)
        enum_extra[value] = entry
    schema["enum"] = enum_values
    schema[ENUM_EXTRA_KEY] = enum_extra


def serialize_one_of_fragment(schema: dict[str, Any], mapped_items: list[MappedItem]) -> None:
    """Write ``oneOf`` branches from mapped items (preserves order)."""
    branches: list[dict[str, Any]] = []
    for mi in mapped_items:
        branch: dict[str, Any] = {"const": mi["value"], "title": mi["label"]}
        for key, val in mi.items():
            if key in ("value", "label"):
                continue
            if key == "description":
                if val is not None:
                    branch["description"] = val
            else:
                branch[f"x-{key}"] = val
        branches.append(branch)
    schema["oneOf"] = branches


SCHEMA_FRAGMENT_SERIALIZERS: dict[str, SchemaFragmentSerializer] = {
    OUTPUT_FORMAT_ENUM: serialize_enum_fragment,
    OUTPUT_FORMAT_ONE_OF: serialize_one_of_fragment,
}


def apply_output_format(schema: dict[str, Any], mapped_items: list[MappedItem], output_format: str) -> None:
    """Mutate ``schema`` using the serializer registered for ``output_format`` (``s_format``)."""
    serializer = SCHEMA_FRAGMENT_SERIALIZERS.get(output_format)
    if serializer is None:
        raise ValueError(f"Unsupported s_format: {output_format}")
    serializer(schema, mapped_items)


# ``ContextVar`` (not ``threading.local``) so the override propagates into ``async`` views and
# tasks scheduled with ``asyncio`` / ``asgiref.sync_to_async``, which carry the current context.
_format_override: ContextVar[str | None] = ContextVar("schemas_output_format_override", default=None)


def get_output_format_override() -> str | None:
    """Return the active override set by :func:`output_format_override`, or ``None``."""
    return _format_override.get()


@contextmanager
def output_format_override(output_format: str) -> Generator[None, None, None]:
    """Force every nested dynamic schema rendered in this context to use ``output_format``.

    Internal callers (e.g. alerting / schema dereferencing) use this to pin a single shape
    regardless of the request's ``s_format`` query parameter or each view's ``default_format``.

    Nested calls stack and restore the previous value on exit.
    """
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output_format: {output_format}. Allowed: {', '.join(sorted(OUTPUT_FORMATS))}")
    token = _format_override.set(output_format)
    try:
        yield
    finally:
        _format_override.reset(token)
