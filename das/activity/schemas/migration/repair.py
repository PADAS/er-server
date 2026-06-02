"""V2 schema collection repair — revision-driven classification.

Background
----------
Earlier versions of the schema migration tool (<= 0.1.3.1) emitted broken
``ui.fields`` entries for collection (array-of-object) fields: nested IDs
used local names instead of dot-prefixed names, ``parent`` references and
``leftColumn`` lists pointed at the wrong containers, and deeply-nested
collections silently dropped their grandchildren. The bug was confined to
the ``ui`` section — the ``json`` section was always structurally correct.

The migration tool team has fixed the bug in 0.1.4 and shipped a
V2-to-V2 repair utility (``repair_v2_schema``) in 0.1.5. This module is
the DAS-side orchestration that decides, per ``EventType``, which of the
four outcomes documented by :class:`RepairStrategy` applies:

* :attr:`RepairStrategy.NOT_MIGRATED` — never V1; nothing to fix.
* :attr:`RepairStrategy.REBUILD_FROM_V1` — re-run the (fixed) migration
  from a reconstructable V1 schema.
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

V1 reconstruction: walk forward from the first revision (sequence 1, full
snapshot) applying each ``ACTION_UPDATED`` diff up to but not including
the migration revision. The result is the V1 ``schema`` text-field value
as it stood immediately before migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

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
    layer re-runs the (fixed) migration tool against the reconstructed V1
    to produce a clean V2 schema."""

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
    return classify(fetch(event_type))


def classify(history: EventTypeRevisionHistory) -> RepairClassification:
    """Pure classification logic — no Django ORM access.

    Drives the strategy decision off the primitives exposed by
    :class:`EventTypeRevisionHistory`. Tests can build a history from
    revision-shaped stubs to exercise this without standing up the
    revision system.
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

    reconstructed, recon_notes = history.schema_just_before_migration()
    if reconstructed is not None:
        return RepairClassification(
            event_type_value=history.event_type_value,
            event_type_id=history.event_type_id,
            strategy=RepairStrategy.REBUILD_FROM_V1,
            migration_revision_sequence=migration.sequence,
            reconstructed_v1_schema=reconstructed,
            notes=recon_notes,
        )

    return RepairClassification(
        event_type_value=history.event_type_value,
        event_type_id=history.event_type_id,
        strategy=RepairStrategy.RECONSTRUCT_FROM_JSON,
        migration_revision_sequence=migration.sequence,
        notes=recon_notes or ["V1 schema not reconstructable from revisions"],
    )
