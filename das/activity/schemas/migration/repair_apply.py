"""Apply layer for V2 schema collection repair.

This module is the bridge between :mod:`activity.schemas.migration.repair`
(pure classification) and the upstream ``schema_migration_tool`` library
(transformation + repair). The sole consumer today is the Django data
migration ``0203_repair_v2_collection_schemas``, which applies the repair
automatically on every environment.

The helper is **pure**: it accepts revision-shaped objects and a schema
text, classifies the EventType, and returns a :class:`RepairOutcome`
describing what should change. The caller decides whether/how to persist.

Strategy dispatch
-----------------

* :attr:`RepairStrategy.NOT_MIGRATED` and
  :attr:`RepairStrategy.SKIP_USER_EDITED` return :class:`RepairOutcome`
  with ``new_schema_text=None`` (no-op).
* An unparseable current V2 JSON text is classified as
  :attr:`RepairStrategy.SKIP_USER_EDITED` by
  :func:`~activity.schemas.migration.repair.classify` (since only a
  manual out-of-band edit can produce non-``json.dumps`` output). The
  ``SKIP_USER_EDITED`` branch returns immediately before reaching the
  repair helpers, so both helpers always receive a parsed dict in
  ``classification.current_v2_schema``.
* :attr:`RepairStrategy.REBUILD_FROM_V1` re-runs ``transform_schema`` on
  the reconstructed V1, then converts each inline hardcoded choice to the
  ``$ref`` form used by V2 choice fields, sourcing the resolved field name
  from ``classification.current_v2_schema``'s intact ``json`` section —
  without any DB access or Choice creation.
* :attr:`RepairStrategy.RECONSTRUCT_FROM_JSON` calls ``repair_v2_schema``
  from the upstream library against ``classification.current_v2_schema``
  (the already-parsed corrupted V2 dict), which infers ``ui.fields`` from
  the JSON section using safe defaults.

Upstream availability
---------------------

The ``schema_migration_tool`` package is a **hard dependency**, pinned at
``==0.1.5.2`` in ``pyproject.toml``. Its symbols (``transform_schema``,
``preprocess_template_vars``, ``repair_v2_schema``, ``LogCollector``) are
imported unconditionally. A missing or partial install fails fast at
import time rather than silently degrading.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from schema_migration_tool import LogCollector, transform_schema
from schema_migration_tool.batch.normalize_export import preprocess_template_vars
from schema_migration_tool.repair import repair_v2_schema

from activity.schemas.ops.revision_history import EventTypeRevisionHistory
from activity.schemas.utils import get_field_schema_from_prop_path

from .choice_processor import ChoiceProcessor
from .repair import RepairClassification, RepairStrategy, classify
from .utils import rewrite_field_to_ref

logger = logging.getLogger(__name__)

# ── Outcome shape ─────────────────────────────────────────────────────────


class RepairAction(str):
    """Free-form action labels for a :class:`RepairOutcome`.

    These are stable strings emitted in structured logs; downstream
    dashboards filter on them. New labels are additive.
    """


SKIPPED_NOT_MIGRATED = "skipped_not_migrated"
SKIPPED_USER_EDITED = "skipped_user_edited"
SKIPPED_ALREADY_CORRECT = "skipped_already_correct"
SKIPPED_NEEDS_REVIEW = "skipped_needs_review"
APPLIED_REBUILT_FROM_V1 = "applied_rebuilt_from_v1"
APPLIED_RECONSTRUCTED_FROM_JSON = "applied_reconstructed_from_json"
ERROR_PARSE = "error_parse"
ERROR_TRANSFORM = "error_transform"
ERROR_REPAIR = "error_repair"
ERROR_UNEXPECTED = "error_unexpected"


@dataclass
class RepairOutcome:
    """Result of attempting repair for a single EventType.

    Attributes
    ----------
    classification:
        The :class:`RepairClassification` produced from the revision history.
    action:
        One of the ``SKIPPED_*``, ``APPLIED_*``, or ``ERROR_*`` constants
        defined above.
    new_schema_text:
        The repaired schema serialised as JSON text. ``None`` for skip
        and error outcomes; the caller is responsible for assigning this
        to ``EventType.schema`` and saving when set.
    errors:
        Free-form error messages collected during the attempt. Empty for
        successful applies and skips.
    metadata:
        Optional structured details (e.g. upstream warning lists, change
        counts from the repair utility) for log enrichment.
    """

    classification: RepairClassification
    action: str
    new_schema_text: str | None = None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def did_apply(self) -> bool:
        return self.new_schema_text is not None


# ── Public entry point ────────────────────────────────────────────────────


def attempt_repair(
    *,
    history: EventTypeRevisionHistory,
    schema_text: str,
) -> RepairOutcome:
    """Classify and (when applicable) repair a single EventType's schema.

    Parameters
    ----------
    history:
        Revision history for the EventType, produced by
        :func:`activity.schemas.ops.revision_history.fetch` (live ORM)
        or :func:`activity.schemas.ops.revision_history.fetch_in_migration`
        (Django data migration body). Carries the ``event_type_value``
        / ``event_type_id`` identifiers used in the resulting
        :class:`RepairClassification` and in error messages.
    schema_text:
        The current ``EventType.schema`` text-field value (V2 schema as
        JSON text). Used directly for the
        :attr:`RepairStrategy.RECONSTRUCT_FROM_JSON` path.
    """
    classification = classify(history, schema_text)

    if classification.strategy == RepairStrategy.NOT_MIGRATED:
        return RepairOutcome(classification=classification, action=SKIPPED_NOT_MIGRATED)

    if classification.strategy == RepairStrategy.SKIP_USER_EDITED:
        return RepairOutcome(classification=classification, action=SKIPPED_USER_EDITED)

    if classification.strategy == RepairStrategy.REBUILD_FROM_V1:
        return _apply_rebuild_from_v1(classification)

    # RECONSTRUCT_FROM_JSON
    return _apply_reconstruct_from_json(classification)


# ── Strategy-specific apply helpers ──────────────────────────────


def _apply_rebuild_from_v1(classification: RepairClassification) -> RepairOutcome:
    """Re-run the migration tool against the reconstructed V1.

    After ``transform_schema`` produces a fresh V2 (with collection fields
    correct), choice fields come out with inline hardcoded choices —
    ``anyOf: [{title: "Hardcoded", oneOf: [...]}]``. This function converts
    each to the ``$ref`` form used by V2 choice fields, sourcing the resolved
    field name from ``classification.current_v2_schema``'s ``json`` section —
    which was unaffected by the collection bug and still holds the correct
    ``$ref`` for each choice field — without any DB access or Choice creation.

    The V1 schema parse (``preprocess_template_vars`` + ``json.loads``) is
    kept local here because it operates on the upstream-preprocessed
    transform input, not on stored data. It is a transform-step concern,
    intentionally decoupled from the stored-data precondition handled by
    ``classify``.

    If a specific field has no ``$ref`` in the corrupted V2 (e.g. it was
    never resolved), the fresh hardcoded field is left as-is and the path
    is logged as unresolved in ``metadata``.
    """
    v1_text = classification.reconstructed_v1_schema
    if not v1_text:
        return RepairOutcome(
            classification=classification,
            action=ERROR_UNEXPECTED,
            errors=[f"{RepairStrategy.REBUILD_FROM_V1.value} strategy reached but reconstructed V1 schema is empty"],
        )

    try:
        normalized_v1_text = preprocess_template_vars(v1_text)
        v1_obj = json.loads(normalized_v1_text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return RepairOutcome(
            classification=classification,
            action=ERROR_PARSE,
            errors=[f"Failed to parse reconstructed V1 schema: {exc}"],
        )

    log_collector = LogCollector({"event_type": classification.event_type_value})
    try:
        v2_obj = transform_schema(v1_obj, log_collector)
    except Exception as exc:  # noqa: BLE001 — upstream call boundary
        return RepairOutcome(
            classification=classification,
            action=ERROR_TRANSFORM,
            errors=[f"transform_schema raised: {type(exc).__qualname__}: {exc}"],
        )

    upstream_errors = [str(e.get("message")) for e in log_collector.get_errors() or []]
    upstream_warnings = [str(w.get("message")) for w in log_collector.get_warnings() or []]
    if upstream_errors:
        return RepairOutcome(
            classification=classification,
            action=ERROR_TRANSFORM,
            errors=upstream_errors,
            metadata={"warnings": upstream_warnings},
        )

    # Re-derive choice $ref URLs from the corrupted V2.  The collection bug
    # was confined to ui.fields; the json section's $ref pointers are intact
    # and encode the resolved choice-field name in each ?field= query param.
    assert classification.current_v2_schema is not None
    corrupted_v2_obj: dict[str, Any] = classification.current_v2_schema
    unresolved_paths: list[list[str]] = []
    hardcoded = ChoiceProcessor().get_hardcoded_choices(v2_obj)
    for hc in hardcoded:
        corrupted_field = get_field_schema_from_prop_path(corrupted_v2_obj, hc.property_path)
        ref_name = _extract_ref_field_name(corrupted_field)
        if ref_name is not None:
            fresh_field = get_field_schema_from_prop_path(v2_obj, hc.property_path)
            if fresh_field is not None:
                rewrite_field_to_ref(fresh_field, ref_name)
        else:
            unresolved_paths.append(hc.property_path)
            logger.warning(
                "repair_apply: no $ref found in corrupted V2 for choice field at path %s "
                "(event_type=%s); leaving hardcoded",
                hc.property_path,
                classification.event_type_value,
            )

    metadata: dict[str, Any] = {"warnings": upstream_warnings}
    if unresolved_paths:
        metadata["unresolved_hardcoded_choice_paths"] = unresolved_paths
        metadata["warnings"] = upstream_warnings + [
            f"Could not re-derive $ref for hardcoded choice field(s) at path(s): "
            f"{unresolved_paths}; fields left with inline choices"
        ]

    return RepairOutcome(
        classification=classification,
        action=APPLIED_REBUILT_FROM_V1,
        new_schema_text=json.dumps(v2_obj, indent=2),
        metadata=metadata,
    )


def _extract_ref_field_name(field_schema: dict | None) -> str | None:
    """Extract the ``?field=NAME`` value from the first ``$ref`` in a field's ``anyOf``.

    Returns ``None`` when:
    - ``field_schema`` is ``None`` (path not found in the corrupted V2),
    - ``anyOf`` is absent or empty,
    - no entry in ``anyOf`` has a ``$ref`` key,
    - the ``$ref`` URL has no ``field`` query parameter, or the value is empty.
    """
    if not field_schema:
        return None
    any_of = field_schema.get("anyOf", [])
    for entry in any_of:
        ref = entry.get("$ref")
        if not ref:
            continue
        parsed = urlparse(ref)
        values = parse_qs(parsed.query).get("field", [])
        name = values[0] if values else None
        if name:
            return name
    return None


def _apply_reconstruct_from_json(
    classification: RepairClassification,
) -> RepairOutcome:
    """Hand the corrupted V2 schema to the upstream V2-to-V2 repair utility.

    The parsed V2 schema is taken from ``classification.current_v2_schema``.

    Per the upstream contract (``==0.1.5.2``,
    ``docs/architecture/v2-schema-repair-upstream-contract.md``):

    * ``repair_v2_schema(v2_schema, logger=LogCollector())`` returns a
      ``RepairResult(repaired_schema, was_modified, changes)``.
    * Errors are reported via the ``logger`` parameter, not by raising.
    * Each ``RepairChange`` carries ``field_path``, ``action``, ``details``
      — surfaced in :attr:`RepairOutcome.metadata` for log correlation.
    * ``result.changes`` can be **non-empty even when ``was_modified=False``**.
      Those entries are diagnostics (actions such as ``skipped_unknown_type``,
      ``ambiguous_collision_kept``, etc.) — corruption beyond the
      collection-key bug that the repair tool refuses to auto-fix.  When
      present, the outcome is :data:`SKIPPED_NEEDS_REVIEW` rather than
      :data:`SKIPPED_ALREADY_CORRECT`, so callers can surface these for
      manual review.
    * Warnings flag lossy-but-correct repairs (e.g. a destroyed COLLECTION
      container rebuilt with defaults).  They are captured in
      ``metadata["warnings"]`` on both applied repairs and needs-review skips.
    """
    assert classification.current_v2_schema is not None
    v2_obj: dict[str, Any] = classification.current_v2_schema

    log_collector = LogCollector({"event_type": classification.event_type_value})
    try:
        result = repair_v2_schema(v2_obj, logger=log_collector)
    except Exception as exc:  # noqa: BLE001 — defensive belt-and-braces
        return RepairOutcome(
            classification=classification,
            action=ERROR_REPAIR,
            errors=[f"repair_v2_schema raised: {type(exc).__qualname__}: {exc}"],
        )

    upstream_errors = [str(e.get("message")) for e in log_collector.get_errors() or []]
    if upstream_errors:
        return RepairOutcome(
            classification=classification,
            action=ERROR_REPAIR,
            errors=upstream_errors,
        )

    was_modified = bool(getattr(result, "was_modified", False))
    repaired_obj = getattr(result, "repaired_schema", v2_obj)
    changes = getattr(result, "changes", []) or []
    upstream_warnings = [str(w.get("message")) for w in log_collector.get_warnings() or []]

    if not was_modified:
        if not changes:
            return RepairOutcome(
                classification=classification,
                action=SKIPPED_ALREADY_CORRECT,
                metadata={"upstream_changes": len(changes)},
            )
        # Diagnostics present but no mutations — queue for manual review.
        return RepairOutcome(
            classification=classification,
            action=SKIPPED_NEEDS_REVIEW,
            metadata={
                "upstream_changes": len(changes),
                # Cap at 25 entries to keep Cloud Logging payloads small while
                # still giving operators enough context to debug surprises.
                "upstream_change_summary": [
                    {
                        "action": getattr(c, "action", ""),
                        "field_path": getattr(c, "field_path", ""),
                        "details": getattr(c, "details", ""),
                    }
                    for c in changes[:25]
                ],
                "warnings": upstream_warnings,
            },
        )

    return RepairOutcome(
        classification=classification,
        action=APPLIED_RECONSTRUCTED_FROM_JSON,
        new_schema_text=json.dumps(repaired_obj, indent=2),
        metadata={
            "upstream_changes": len(changes),
            # Cap at 25 entries to keep Cloud Logging payloads small while
            # still giving operators enough context to debug surprises.
            "upstream_change_summary": [
                {
                    "action": getattr(c, "action", ""),
                    "field_path": getattr(c, "field_path", ""),
                    "details": getattr(c, "details", ""),
                }
                for c in changes[:25]
            ],
            "warnings": upstream_warnings,
        },
    )
