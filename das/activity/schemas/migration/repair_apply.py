"""Apply layer for V2 schema collection repair.

This module is the bridge between :mod:`activity.schemas.migration.repair`
(pure classification) and the upstream ``schema_migration_tool`` library
(transformation + repair). The sole consumer today is the Django data
migration ``0202_repair_v2_collection_schemas``, which applies the repair
automatically on every environment.

The helper is **pure**: it accepts revision-shaped objects and a schema
text, classifies the EventType, and returns a :class:`RepairOutcome`
describing what should change. The caller decides whether/how to persist.

Strategy dispatch
-----------------

* :attr:`RepairStrategy.NOT_MIGRATED` and
  :attr:`RepairStrategy.SKIP_USER_EDITED` return :class:`RepairOutcome`
  with ``new_schema_text=None`` (no-op).
* :attr:`RepairStrategy.REBUILD_FROM_V1` re-runs ``transform_schema`` on
  the reconstructed V1 (this is the entry point that 0.1.4 fixed).
* :attr:`RepairStrategy.RECONSTRUCT_FROM_JSON` calls ``repair_v2_schema``
  from the upstream library, which infers ``ui.fields`` from the JSON
  section using safe defaults. The branch automatically short-circuits
  to ``SKIPPED_JSON_RECONSTRUCTION_DEFERRED`` when the upstream is not
  importable (the :data:`REPAIR_V2_AVAILABLE` gate).

Upstream availability
---------------------

``repair_v2_schema`` ships under ``schema_migration_tool.repair`` and is
pinned at ``>=0.1.5`` in ``pyproject.toml``. The :data:`REPAIR_V2_AVAILABLE`
flag and the surrounding ``try/except ImportError`` are kept as defensive
gates only — in practice the symbol resolves on every supported
environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from activity.schemas.ops.revision_history import EventTypeRevisionHistory

from .repair import RepairClassification, RepairStrategy, classify

# ── Upstream availability detection ──────────────────────────────────────


try:
    from schema_migration_tool import LogCollector, transform_schema
    from schema_migration_tool.batch.normalize_export import preprocess_template_vars

    TRANSFORM_AVAILABLE = True
except ImportError:  # pragma: no cover — defensive
    TRANSFORM_AVAILABLE = False
    LogCollector = None  # type: ignore[assignment]
    transform_schema = None  # type: ignore[assignment]
    preprocess_template_vars = None  # type: ignore[assignment]

try:
    # Public API per the migration-tool team's handover
    # (``docs/architecture/v2-schema-repair-upstream-contract.md``):
    # the repair function ships under the ``schema_migration_tool.repair``
    # submodule, introduced in v0.1.5. The pin in ``pyproject.toml``
    # enforces ``>=0.1.5``; the try/except remains as a defensive gate
    # for non-standard install layouts.
    from schema_migration_tool.repair import repair_v2_schema

    REPAIR_V2_AVAILABLE = True
except ImportError:  # pragma: no cover — pin enforces availability
    REPAIR_V2_AVAILABLE = False
    repair_v2_schema = None  # type: ignore[assignment]


# ── Outcome shape ─────────────────────────────────────────────────────────


class RepairAction(str):
    """Free-form action labels for a :class:`RepairOutcome`.

    These are stable strings emitted in structured logs; downstream
    dashboards filter on them. New labels are additive.
    """


SKIPPED_NOT_MIGRATED = "skipped_not_migrated"
SKIPPED_USER_EDITED = "skipped_user_edited"
SKIPPED_JSON_RECONSTRUCTION_DEFERRED = "skipped_json_reconstruction_deferred"
SKIPPED_ALREADY_CORRECT = "skipped_already_correct"
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
    classification = classify(history)

    if classification.strategy == RepairStrategy.NOT_MIGRATED:
        return RepairOutcome(classification=classification, action=SKIPPED_NOT_MIGRATED)

    if classification.strategy == RepairStrategy.SKIP_USER_EDITED:
        return RepairOutcome(classification=classification, action=SKIPPED_USER_EDITED)

    if classification.strategy == RepairStrategy.REBUILD_FROM_V1:
        return _apply_rebuild_from_v1(classification)

    # RECONSTRUCT_FROM_JSON — short-circuit only if upstream is missing.
    if not REPAIR_V2_AVAILABLE:
        return RepairOutcome(
            classification=classification,
            action=SKIPPED_JSON_RECONSTRUCTION_DEFERRED,
            metadata={"repair_v2_available": False},
        )
    return _apply_reconstruct_from_json(classification, schema_text)


# ── Strategy-specific apply helpers ──────────────────────────────


def _apply_rebuild_from_v1(classification: RepairClassification) -> RepairOutcome:
    """Re-run the (now-fixed) migration tool against the reconstructed V1."""
    if not TRANSFORM_AVAILABLE:  # pragma: no cover — pyproject pins schema_migration_tool >=0.1.5
        return RepairOutcome(
            classification=classification,
            action=ERROR_UNEXPECTED,
            errors=["schema_migration_tool transform_schema is not importable"],
        )
    # Narrow the optional imports for the type checker; the gate above guarantees
    # all three symbols are non-None at this point.
    assert preprocess_template_vars is not None
    assert transform_schema is not None
    assert LogCollector is not None

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

    return RepairOutcome(
        classification=classification,
        action=APPLIED_REBUILT_FROM_V1,
        new_schema_text=json.dumps(v2_obj, indent=2),
        metadata={"warnings": upstream_warnings},
    )


def _apply_reconstruct_from_json(
    classification: RepairClassification,
    schema_text: str,
) -> RepairOutcome:
    """Hand the corrupted V2 schema to the upstream V2-to-V2 repair utility.

    Per the migration-tool team's contract
    (``docs/architecture/v2-schema-repair-upstream-contract.md``):

    * ``repair_v2_schema(v2_schema, logger=LogCollector())`` returns a
      ``RepairResult(repaired_schema, was_modified, changes)``.
    * Errors are reported via the ``logger`` parameter, not by raising.
    * Each ``RepairChange`` carries ``field_path``, ``action``, ``details``
      — surfaced in :attr:`RepairOutcome.metadata` for log correlation.
    """
    # ``attempt_repair`` already guards on REPAIR_V2_AVAILABLE before
    # routing here; the asserts narrow the optional imports for the type
    # checker (the pin in pyproject.toml guarantees both are non-None).
    assert repair_v2_schema is not None
    assert LogCollector is not None

    try:
        v2_obj = json.loads(schema_text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return RepairOutcome(
            classification=classification,
            action=ERROR_PARSE,
            errors=[f"Failed to parse current V2 schema: {exc}"],
        )

    log_collector = LogCollector({"event_type": classification.event_type_value})
    repair_call: Callable[..., Any] = repair_v2_schema  # type: ignore[assignment]
    try:
        result = repair_call(v2_obj, logger=log_collector)
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

    if not was_modified:
        return RepairOutcome(
            classification=classification,
            action=SKIPPED_ALREADY_CORRECT,
            metadata={"upstream_changes": 0},
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
        },
    )
