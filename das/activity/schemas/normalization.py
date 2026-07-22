"""Normalizes legacy V2 event-type schema documents into current-spec shape.

Users copy schemas between EarthRanger sites, and integrations submit schemas produced by
older form-builder versions and/or the Event-Type-Schema-Migration-Tool; as the metaschema evolves,
these "stale but once-valid" documents fail validation even though the form-builder UI still
understands them. This module rewrites the known legacy shapes below, on a copy, before
``JSONSchemaField`` validates.

Add a new legacy shape by adding one ``(name, transform)`` entry to ``_TRANSFORMS``.
"""

from __future__ import annotations

import copy
import logging
from typing import Callable, TypeAlias

from activity.schemas.utils import get_field_schema_from_prop_path, is_v2_schema

logger = logging.getLogger(__name__)

JSONDict: TypeAlias = "dict[str, object]"
# A transform mutates the document in place and reports whether it changed anything.
_Transform: TypeAlias = Callable[[JSONDict], bool]


def _additional_properties_to_unevaluated(node: object) -> bool:
    """Recursively rewrite ``additionalProperties: false`` -> ``unevaluatedProperties: false``.

    Only the boolean ``False`` triggers the rewrite -- a dict-valued
    ``additionalProperties`` is a different (schema-composition) construct and is left
    alone. Ref: Event-Type-Schema-Migration-Tool PR #11 (v1.4.1); before das's ERA-13041
    metaschema refactor (9525bd3bf), collection ``items`` accepted either key via
    ``"oneOf": [{"required": ["additionalProperties"]}, {"required": ["unevaluatedProperties"]}]``.
    """
    changed = False
    if isinstance(node, dict):
        if node.get("additionalProperties") is False:
            del node["additionalProperties"]
            node.setdefault("unevaluatedProperties", False)
            changed = True
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return False
    # We are in a dict or list, so walk children recursively
    for child in children:
        changed = _additional_properties_to_unevaluated(child) or changed
    return changed


def _additional_properties_transform(document: JSONDict) -> bool:
    """Walk ``document["json"]`` only (never ``ui``)."""
    json_node = document.get("json")
    return isinstance(json_node, dict) and _additional_properties_to_unevaluated(json_node)


def _add_unevaluated_items(document: JSONDict) -> bool:
    """Add ``unevaluatedItems: false`` to COLLECTION field arrays that lack it.

    Discriminates collections from attachment arrays via ``ui.fields[<id>].type``
    (``"COLLECTION"`` vs ``"ATTACHMENT"``) rather than by shape, since both are
    ``type: array`` in ``json``. This is load-bearing, not cosmetic: the attachment
    metaschema is ``additionalProperties: False`` with no ``unevaluatedItems`` in its
    properties, so it would *reject* an attachment array carrying the key. Nested
    collections (dotted ui ids like ``arrests.items_confiscated``) are handled because
    each ``ui.fields`` entry is resolved independently via its own dotted path -- same
    traversal ``activity.schemas.utils.get_field_schema_from_prop_path`` uses for reads.

    Provenance: not the migration tool -- PR #11's diff shows ``unevaluatedItems`` already
    present. Before das's ERA-13041 metaschema refactor (9525bd3bf), ``collection_field_schema``
    had no top-level ``required`` list, so the key was optional; schemas saved before then
    can legitimately lack it.
    """
    ui_node = document.get("ui")
    ui_fields = ui_node.get("fields") if isinstance(ui_node, dict) else None
    if not isinstance(ui_fields, dict) or not isinstance(document.get("json"), dict):
        return False

    changed = False
    for field_id, ui_field in ui_fields.items():
        if not isinstance(ui_field, dict) or ui_field.get("type") != "COLLECTION":
            continue
        field_schema = get_field_schema_from_prop_path(document, field_id.split("."))
        if isinstance(field_schema, dict) and "unevaluatedItems" not in field_schema:
            field_schema["unevaluatedItems"] = False
            changed = True
    return changed


def _pop_legacy_ui_choices(document: JSONDict) -> bool:
    """Drop the legacy ``choices`` key from ``ui.fields`` entries.

    Never touches ``x-dynamic-choice`` markers or anything else in the field -- that
    belongs to a different, unrelated migration flow (ERA-13508). Ref:
    Event-Type-Schema-Migration-Tool PR #13 (v0.1.6); before das's ERA-13041 metaschema
    refactor, ``ui_choice_schema`` had ``"required": ["choices", "inputType", "parent", "type"]``
    -- ``choices`` was mandatory on ui choice fields back then.
    """
    ui_node = document.get("ui")
    ui_fields = ui_node.get("fields") if isinstance(ui_node, dict) else None
    if not isinstance(ui_fields, dict):
        return False

    changed = False
    for ui_field in ui_fields.values():
        if isinstance(ui_field, dict) and "choices" in ui_field:
            del ui_field["choices"]
            changed = True
    return changed


_TRANSFORMS: tuple[tuple[str, _Transform], ...] = (
    ("additional_properties_to_unevaluated_properties", _additional_properties_transform),
    ("add_unevaluated_items_to_collections", _add_unevaluated_items),
    ("pop_legacy_ui_choices", _pop_legacy_ui_choices),
)


def normalize_v2_schema(document: JSONDict) -> JSONDict:
    """Normalize known legacy shapes in a V2 event-type schema document.

    Only V2-shaped documents (a dict with both ``"json"`` and ``"ui"`` keys) are touched;
    anything else is returned as-is. ``document`` itself is never mutated -- a copy is
    normalized and returned. Idempotent: normalizing an already-current document is a
    no-op, and normalizing twice equals normalizing once.
    """
    if not is_v2_schema(document):
        return document

    normalized = copy.deepcopy(document)
    applied = [name for name, transform in _TRANSFORMS if transform(normalized)]

    if applied:
        logger.info(
            "Normalized legacy V2 event-type schema document; transforms applied: %s",
            ", ".join(applied),
        )

    return normalized
