"""V2 schema collection repair — revision-driven classification.

The collection bug in V2 schema migration affected only the ``ui.fields``
section: nested IDs used local names instead of dot-prefixed names,
``parent`` references and ``leftColumn`` lists pointed at the wrong
containers, and deeply-nested collections silently dropped their
grandchildren. The ``json`` section is the source of truth and was
unaffected.

This module is the DAS-side orchestration that decides, per ``EventType``,
which of the four outcomes documented by :class:`RepairStrategy` applies:

* :attr:`RepairStrategy.NOT_MIGRATED` — never V1; nothing to fix.
* :attr:`RepairStrategy.REBUILD_FROM_V1` — re-run the migration tool
  against the reconstructed V1 schema.
* :attr:`RepairStrategy.RECONSTRUCT_FROM_JSON` — hand the corrupted V2
  schema to the upstream repair utility, which infers the correct
  ``ui.fields`` from the JSON section using safe defaults.
* :attr:`RepairStrategy.SKIP_USER_EDITED` — user has manually edited
  the V2 schema after migration; respect their changes.

Detection rules
---------------
Migration revision: an ``ACTION_UPDATED`` revision whose ``data`` dict
contains BOTH ``schema`` and ``version`` keys, with ``data["version"] ==
"2"``. The DAS revision system stores diff-only payloads for updates, so
the simultaneous presence of those two keys is an unambiguous fingerprint
of a V1 -> V2 flip.

Post-migration user edit: any revision after the migration revision whose
``data`` dict contains ``schema``.

V1 reconstruction: take the ``schema`` value of the latest revision that
carries one strictly before the migration revision. The DAS revision
system records the field's full text verbatim on every write, so no
``ACTION_ADDED`` snapshot anchor is required — a truncated history (or a
snapshot lacking a ``schema`` field) is still reconstructable as long as
some pre-migration revision set one. The result is the V1 ``schema``
text-field value as it stood immediately before migration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from activity.schemas.ops.revision_history import EventTypeRevisionHistory, fetch


class RepairStrategy(str, Enum):
    """Classification outcome for a single EventType — the strategy that
    the apply layer will use (or the reason no repair will be attempted).

    Each value is a stable string identifier used in structured logs,
    CSV exports, and dashboard filters. Keep them self-describing so a
    future reader doesn't have to chase definitions.
    """

    NOT_MIGRATED = "not_migrated"
    """The EventType is V2 today but no migration revision was found in its
    history. Most likely the EventType was created post-migration-tool, or
    its revisions were truncated. Nothing to repair from revisions."""

    REBUILD_FROM_V1 = "rebuild_from_v1"
    """Migration revision found, no post-migration user edits, and the V1
    schema can be reconstructed from pre-migration revisions. The apply
    layer re-runs the migration tool against the reconstructed V1 to
    produce a clean V2 schema."""

    RECONSTRUCT_FROM_JSON = "reconstruct_from_json"
    """Migration revision found, no post-migration user edits, but V1 is
    not reconstructable. The apply layer hands the corrupted V2 schema to
    the upstream V2-to-V2 repair utility (``repair_v2_schema``), which
    reconstructs ``ui.fields`` from the JSON section using safe defaults."""

    SKIP_USER_EDITED = "skip_user_edited"
    """Migration revision found AND at least one post-migration revision
    modified ``schema``. Skip — respect the user's manual changes."""


@dataclass
class RepairClassification:
    """Per-EventType classification result.

    Attributes
    ----------
    event_type_value:
        The ``EventType.value`` slug.
    event_type_id:
        The ``EventType.id`` UUID, str-coerced for logging.
    strategy:
        See :class:`RepairStrategy`.
    migration_revision_sequence:
        Sequence number of the detected migration revision, or ``None`` if
        no migration revision was found.
    post_migration_schema_edits:
        Count of revisions after the migration revision that touched
        ``schema``. Always 0 for strategies other than
        :attr:`RepairStrategy.SKIP_USER_EDITED`.
    reconstructed_v1_schema:
        Reconstructed pre-migration ``schema`` text-field value when
        ``strategy == RepairStrategy.REBUILD_FROM_V1``, otherwise ``None``.
    notes:
        Free-form diagnostic strings useful for the run report (e.g.
        "snapshot revision missing schema field").
    """

    event_type_value: str
    event_type_id: str
    strategy: RepairStrategy
    migration_revision_sequence: int | None = None
    post_migration_schema_edits: int = 0
    reconstructed_v1_schema: str | None = None
    notes: list[str] = field(default_factory=list)
    current_v2_schema: dict[str, Any] | None = None


# ── Public API ────────────────────────────────────────────────────────────


def classify_event_type(event_type) -> RepairClassification:
    """Classify a single ``EventType`` for repair.

    Convenience wrapper for live callers — fetches the revision history
    via :func:`activity.schemas.ops.revision_history.fetch` and runs
    :func:`classify`. The ``event_type`` argument must be a concrete
    model instance (not a historical app-registry model) because
    :func:`fetch` uses the ``revision`` descriptor.

    For Django data migration bodies, fetch the history with
    :func:`activity.schemas.ops.revision_history.fetch_in_migration` and
    call :func:`classify` directly.
    """
    return classify(fetch(event_type), event_type.schema or "")


def classify(history: EventTypeRevisionHistory, current_v2_text: str) -> RepairClassification:
    """Pure classification logic — no Django ORM access.

    Drives the strategy decision off the primitives exposed by
    :class:`EventTypeRevisionHistory`. Tests can build a history from
    revision-shaped stubs to exercise this without standing up the
    revision system.

    The ``current_v2_text`` argument is the current ``EventType.schema``
    JSON text (the potentially corrupted V2). It is parsed here once, as
    the third gate after the two history-based checks, so that the apply
    layer can rely on an already-validated ``classification.current_v2_schema``
    dict rather than re-parsing. If the current V2 is not valid JSON, it
    cannot have been emitted by the migration tool (which always writes via
    ``json.dumps``), so it must be the result of a manual out-of-band edit —
    treat it as a user modification and return :attr:`RepairStrategy.SKIP_USER_EDITED`
    immediately without consulting the history-based strategy gates that follow.
    For valid JSON the parsed dict is attached to the classification so the
    apply layer never re-parses.
    """
    migration = history.migration_revision()
    if migration is None:
        return RepairClassification(
            event_type_value=history.event_type_value,
            event_type_id=history.event_type_id,
            strategy=RepairStrategy.NOT_MIGRATED,
            notes=["no migration revision (schema+version flip) found in history"],
        )

    post_edits = history.post_migration_schema_edit_count()
    if post_edits > 0:
        return RepairClassification(
            event_type_value=history.event_type_value,
            event_type_id=history.event_type_id,
            strategy=RepairStrategy.SKIP_USER_EDITED,
            migration_revision_sequence=migration.sequence,
            post_migration_schema_edits=post_edits,
            notes=[f"{post_edits} post-migration revision(s) modified schema; skipping"],
        )

    try:
        parsed: dict[str, Any] = json.loads(current_v2_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return RepairClassification(
            event_type_value=history.event_type_value,
            event_type_id=history.event_type_id,
            strategy=RepairStrategy.SKIP_USER_EDITED,
            migration_revision_sequence=migration.sequence,
            notes=["current V2 schema is not valid JSON; treating as user-modified and skipping"],
        )

    reconstructed, recon_notes = history.schema_just_before_migration()
    if reconstructed is not None:
        return RepairClassification(
            event_type_value=history.event_type_value,
            event_type_id=history.event_type_id,
            strategy=RepairStrategy.REBUILD_FROM_V1,
            migration_revision_sequence=migration.sequence,
            reconstructed_v1_schema=reconstructed,
            notes=recon_notes,
            current_v2_schema=parsed,
        )

    return RepairClassification(
        event_type_value=history.event_type_value,
        event_type_id=history.event_type_id,
        strategy=RepairStrategy.RECONSTRUCT_FROM_JSON,
        migration_revision_sequence=migration.sequence,
        notes=recon_notes or ["V1 schema not reconstructable from revisions"],
        current_v2_schema=parsed,
    )
