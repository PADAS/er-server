"""Shared schema utilities for the activity.schemas package."""

from __future__ import annotations


def is_v2_schema(document: object) -> bool:
    """Return whether ``document`` has the top-level shape of a V2 schema."""
    return isinstance(document, dict) and "json" in document and "ui" in document


def is_v1_schema(document: object) -> bool:
    """Return whether ``document`` has the top-level shape of a V1 schema."""
    return isinstance(document, dict) and "schema" in document and "definition" in document


def get_field_schema_from_prop_path(v2_schema: dict, prop_path: list[str]) -> dict | None:
    """Get the field schema from a v2_schema, following the property path.

    Traverses ``v2_schema["json"]["properties"]`` step by step.  When a step
    resolves to an ``array`` type the traversal descends into
    ``items.properties``; for an ``object`` type it descends into
    ``properties``.  Returns ``None`` if any segment of the path is absent or
    if an intermediate segment resolves to a scalar type (a type that cannot
    be descended into, e.g. ``"string"`` or ``"number"``).  This prevents a
    sideways jump where the next segment would otherwise be matched against
    siblings at the same level rather than children of the resolved field.
    """
    current_properties = v2_schema.get("json", {}).get("properties", {})
    field_schema = {}

    for field_name in prop_path:
        if field_name not in current_properties:
            return None
        field_schema = current_properties[field_name]

        if not isinstance(field_schema, dict):
            return None

        field_type = field_schema.get("type")
        if field_type == "array":
            sub_tree = field_schema.get("items", {}).get("properties", {})
            current_properties = sub_tree if isinstance(sub_tree, dict) else {}
        elif field_type == "object":
            sub_tree = field_schema.get("properties", {})
            current_properties = sub_tree if isinstance(sub_tree, dict) else {}
        else:
            # Scalar type (string, number, boolean, …) — cannot descend further.
            # Set current_properties to empty so any subsequent segment lookup
            # returns None rather than matching a sibling field.
            current_properties = {}

    return field_schema
