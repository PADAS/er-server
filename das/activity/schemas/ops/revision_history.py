"""Revision-history-aware EventType schema lifecycle primitives.

Single home for "walk an ``EventType``'s revision history and answer a
schema-shaped question". Consumed by the V1→V2 collection repair today
(see :mod:`activity.schemas.migration`) and reserved for the planned
``revision_diff`` / ``revision_restore`` / ``revision_as_of`` /
``ad_hoc_repair`` ops described in :mod:`activity.schemas.ops`.

Layered design
--------------

Three layers, each callable on its own:

1. :class:`RevisionLike` — typing-only protocol pinning the duck-typed
   contract used throughout (``sequence``, ``action``, ``data``).
2. :class:`EventTypeRevisionHistory` — pure-Python value object wrapping
   a sequence-ascending tuple of revisions. **All** schema-lifecycle
   queries live here. No Django imports; trivially exercisable from
   tests with hand-built revision-shaped objects.
3. :func:`fetch` / :func:`fetch_in_migration` — thin Django adapters
   that produce a history. The only place ORM access happens.

Why a dedicated module
----------------------

Centralising the schema-lifecycle primitives here means future ops
(``revision_as_of``, ``revision_restore``, etc.) share the same
V1→V2 fingerprint logic and diff-replay loop — one place to answer
"where is the migration revision detected?"

V2-schema oriented; not a general-purpose audit timeline
--------------------------------------------------------

Audit-timeline UI flows (events, patrols, files, …) keep using
:meth:`revision.manager.RevisionManager.all_user`: those are
user-prefetched, paginated, and shaped for display. This module is for
analytical / mutation flows on EventType schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol
from uuid import UUID

# Action string constants kept in sync with :mod:`revision.manager`. They are
# inlined (not imported) so this module can be loaded and unit-tested without
# triggering Django's app-registry, in keeping with the "Layered design" claim
# above. The revision system stores these strings verbatim in
# ``EventTypeRevision.action`` rows, so they are a stable data-shape contract
# rather than evolving internal API. A guard test in
# ``activity/tests/test_revision_history.py`` asserts they remain identical to
# the values exported from :mod:`revision.manager`.
ACTION_ADDED = "added"
ACTION_UPDATED = "updated"

# ── Layer 1: typing protocol ──────────────────────────────────────────────


class RevisionLike(Protocol):
    """Duck-typed contract for any revision-shaped object.

    Satisfied by:

    * Real ``EventTypeRevision`` rows from the live ORM.
    * Historical ``EventTypeRevision`` rows obtained via
      ``apps.get_model("activity", "EventTypeRevision")`` inside a Django
      data migration body.
    * Test stubs (any ``@dataclass`` with the three attributes below).

    Notes
    -----
    ``data`` is the JSONField text of the diff (or full snapshot for
    ``ACTION_ADDED``). In practice ``Mapping[str, Any] | None`` at
    runtime, but typed as ``Any`` here so concrete implementations can
    declare the attribute as ``dict[str, Any]`` (the common dataclass
    spelling) without falling foul of Protocol attribute invariance.
    All consumers must funnel reads through :func:`_data_dict` to
    defend against ``None``.
    """

    sequence: int
    action: str
    data: Any


def _data_dict(revision: RevisionLike) -> Mapping[str, Any]:
    """Coerce ``revision.data`` to a Mapping, defending against legacy
    rows that stored ``None`` in the JSONField."""
    data = revision.data
    if isinstance(data, Mapping):
        return data
    return {}


# ── Layer 2: pure history object ──────────────────────────────────────────


@dataclass(frozen=True)
class EventTypeRevisionHistory:
    """A V2-schema-oriented projection of an ``EventType``'s revision
    history.

    Always sorted by ``sequence`` ascending. Methods are pure Python so
    they can be exercised in tests with hand-built revision-shaped
    stubs.

    Attributes
    ----------
    event_type_value:
        The ``EventType.value`` slug. Carried through so callers don't
        need to re-thread it alongside the history.
    event_type_id:
        The ``EventType.id`` UUID, str-coerced for logging consistency.
    revisions:
        Sequence-ascending tuple of revision-shaped objects.
    """

    event_type_value: str
    event_type_id: str
    revisions: tuple[RevisionLike, ...]

    @classmethod
    def from_revisions(
        cls,
        *,
        event_type_value: str,
        event_type_id: str,
        revisions: Iterable[RevisionLike],
    ) -> EventTypeRevisionHistory:
        """Build a history, sorting the input by ``sequence`` ascending.

        The input order is not trusted: ORM callers usually provide
        ascending order already, but tests and migration callers may not.
        """
        ordered = tuple(sorted(revisions, key=lambda r: r.sequence))
        return cls(
            event_type_value=event_type_value,
            event_type_id=event_type_id,
            revisions=ordered,
        )

    # ── Detection primitives ──────────────────────────────────────────────

    def creation_snapshot(self) -> RevisionLike | None:
        """Return the ``ACTION_ADDED`` snapshot, if any.

        By revision-system convention this is the first revision
        (``sequence == 1``) and carries the full serialized model state
        in ``data``. Anomalous histories (no creation row, or creation
        row not at sequence 1) return whatever ``ACTION_ADDED`` row is
        first by sequence.
        """
        return next(
            (r for r in self.revisions if r.action == ACTION_ADDED),
            None,
        )

    def migration_revision(self) -> RevisionLike | None:
        """Return the V1→V2 migration revision, if any.

        The fingerprint is an ``ACTION_UPDATED`` revision whose ``data``
        dict contains BOTH ``schema`` and ``version`` keys with
        ``version == "2"``. The DAS revision system stores diff-only
        payloads on updates, so the simultaneous presence of those two
        keys is an unambiguous fingerprint of a V1→V2 flip.

        If multiple matching revisions exist (theoretically impossible
        — once an EventType is V2 it cannot be flipped back through the
        API — but possible via direct DB writes) the first one by
        sequence wins. Detecting and surfacing the anomaly is the
        caller's responsibility.
        """
        for revision in self.revisions:
            if revision.action != ACTION_UPDATED:
                continue
            data = _data_dict(revision)
            if "schema" in data and "version" in data and str(data.get("version")) == "2":
                return revision
        return None

    def revisions_modifying(
        self,
        field: str,
        *,
        after: int | None = None,
    ) -> list[RevisionLike]:
        """Return ``ACTION_UPDATED`` revisions whose ``data`` carries a
        diff for ``field``.

        Parameters
        ----------
        field:
            JSON key to look for in each ``revision.data`` dict.
        after:
            If provided, exclude revisions with ``sequence <= after``.
            Use ``migration_revision().sequence`` to express
            "post-migration edits".
        """
        result: list[RevisionLike] = []
        for revision in self.revisions:
            if revision.action != ACTION_UPDATED:
                continue
            if after is not None and revision.sequence <= after:
                continue
            data = _data_dict(revision)
            if field in data:
                result.append(revision)
        return result

    # ── Schema time-travel ────────────────────────────────────────────────

    def schema_at(self, sequence: int) -> str | None:
        """Reconstruct the value of ``EventType.schema`` as it stood
        immediately after the revision at ``sequence``.

        Walks every revision with ``revision.sequence <= sequence`` and
        tracks the latest one whose ``data`` carries a ``schema`` key.
        Because the DAS revision system records the field's **full text
        value verbatim** on every write — the ``ACTION_ADDED`` snapshot
        *and* each ``ACTION_UPDATED`` diff that touches ``schema`` — the
        most recent schema-bearing revision at or before ``sequence``
        already holds the complete schema text. No creation snapshot is
        required as an anchor: a history whose ``ACTION_ADDED`` row is
        missing (e.g. a truncated export) or lacks a ``schema`` field is
        still reconstructable as long as *some* revision at or before
        ``sequence`` carries one.

        The reconstruction works for both V1 schemas (raw text) and V2
        schemas (JSON text) — the schema *language version* is a separate
        question for the caller (consult :meth:`migration_revision` to
        know whether the result is V1 or V2).

        Returns
        -------
        ``str``
            The schema text as stored after the targeted revision.
        ``None``
            * No revision at or before ``sequence`` carries a ``schema``
              key.
            * The most recent schema-bearing revision set ``schema`` to a
              non-string value (e.g. an UPDATE that explicitly set it to
              ``None``).
        """
        current: object = None
        found = False
        for revision in self.revisions:
            if revision.sequence > sequence:
                break
            data = _data_dict(revision)
            if "schema" in data:
                current = data.get("schema")
                found = True

        if not found:
            return None
        if not isinstance(current, str):
            return None
        return current

    # ── Convenience derivatives ──────────────────────────────────────────

    def schema_just_before_migration(
        self,
    ) -> tuple[str | None, list[str]]:
        """Reconstruct the V1 ``schema`` text as it stood the instant
        before the V1→V2 migration revision.

        Returns ``(schema_text, notes)``. ``notes`` is empty on the happy
        path and populated with diagnostic strings when reconstruction is
        not possible — the caller surfaces these in classification
        results / structured logs.
        """
        notes: list[str] = []

        migration = self.migration_revision()
        if migration is None:
            notes.append("no migration revision (schema+version flip) found in history")
            return None, notes

        # Reconstruct from the latest schema-bearing revision strictly
        # before the migration. :meth:`schema_at` does not require a
        # creation snapshot — any pre-migration revision carrying a
        # ``schema`` value is a valid anchor (the field is stored
        # verbatim, not as a structural sub-diff), so truncated histories
        # and snapshots that lack a ``schema`` field are still
        # reconstructable as long as some earlier revision set one.
        schema = self.schema_at(migration.sequence - 1)
        if schema is None:
            notes.append(
                "no schema-bearing revision found before the migration revision "
                "(history may be truncated, or schema was never set pre-migration)"
            )
            return None, notes
        if not schema.strip():
            notes.append("reconstruction yielded an empty schema value")
            return None, notes

        return schema, notes

    def post_migration_schema_edit_count(self) -> int:
        """Number of ``ACTION_UPDATED`` revisions strictly after the
        migration revision whose ``data`` carries a ``schema`` diff.

        Returns ``0`` when there is no migration revision in the history
        (there is no "post-migration" window to count in).
        """
        migration = self.migration_revision()
        if migration is None:
            return 0
        return len(self.revisions_modifying("schema", after=migration.sequence))


# ── Layer 3: Django-aware fetch helpers ──────────────────────────────────


def fetch(event_type) -> EventTypeRevisionHistory:
    """Build a history from a live ``EventType`` model instance.

    Uses the ``revision`` descriptor attached by
    :class:`revision.manager.Revision`. Always returns sequence-ascending.

    Use this from services, views, management commands, and tests that
    have a live ORM-attached instance. For Django data migrations, use
    :func:`fetch_in_migration` instead — historical app-registry models
    do not have the descriptor attached.
    """
    rows = list(event_type.revision.all().order_by("sequence"))
    return EventTypeRevisionHistory.from_revisions(
        event_type_value=str(event_type.value),
        event_type_id=str(event_type.id),
        revisions=rows,
    )


def fetch_in_migration(
    event_type,
    *,
    revision_model,
    db_alias: str,
    tenant_id: UUID | str,
) -> EventTypeRevisionHistory:
    """Build a history inside a Django data migration body.

    Migration bodies cannot use the live ``revision`` descriptor — the
    historical app-registry models have no descriptors attached. This
    helper performs the equivalent ``filter(...).order_by("sequence")``
    using the historical ``EventTypeRevision`` model passed by the
    caller, wrapped in :class:`UnsetDASTenantContextManager` so the
    tenant-scoped manager mixin doesn't reject the explicit
    ``das_tenant_id`` filter. It is the reference implementation of the
    migration-safe ``values_list(..., named=True)`` revision read documented
    in ``AGENTS.md``; kept and tested for future migrations even though the
    only repair that used it now runs as the ``repair_v2_collection_schemas``
    command.

    Parameters
    ----------
    event_type:
        Historical EventType instance (the row whose revisions we want).
    revision_model:
        Resolved via ``apps.get_model("activity", "EventTypeRevision")``
        in the migration body.
    db_alias:
        From ``schema_editor.connection.alias`` so the query is bound to
        the correct database — important for multi-DB setups.
    tenant_id:
        UUID of the tenant whose revisions to read. Required because
        the migration body explicitly per-tenants its work and the
        manager-mixin tenant filter is bypassed inside
        ``UnsetDASTenantContextManager``.
    """
    # Imported lazily so :class:`EventTypeRevisionHistory` and the rest of
    # this module stay free of Django-app-registry-bound imports at module
    # import time. ``utils.tenant.managers`` transitively pulls in Django
    # multitenant pieces; deferring keeps unit-testing the pure history
    # primitives lightweight.
    from utils.tenant.managers import UnsetDASTenantContextManager

    with UnsetDASTenantContextManager():
        # IMPORTANT: read revisions as ``values_list(..., named=True)`` Row
        # tuples rather than model instances. The historical ``EventTypeRevision``
        # model (from ``apps.get_model``) is a ``__fake__`` TenantModel whose
        # ``tenant_id`` class attribute is dropped by migration-state rendering,
        # so constructing instances raises AttributeError under
        # django_multitenant. ``RevisionLike`` only needs ``.sequence`` /
        # ``.action`` / ``.data``, all of which a named Row provides — and
        # ``.values_list`` never instantiates the model. Do not "simplify" this
        # back to ``list(...objects...)``.
        rows = list(
            revision_model.objects.using(db_alias)
            .filter(object_id=event_type.id, das_tenant_id=tenant_id)
            .order_by("sequence")
            .values_list("sequence", "action", "data", named=True)
        )
    return EventTypeRevisionHistory.from_revisions(
        event_type_value=str(event_type.value),
        event_type_id=str(event_type.id),
        revisions=rows,
    )
