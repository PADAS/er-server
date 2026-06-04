"""Schema lifecycle operations namespace.

This package is the home for **revision-history-aware schema lifecycle
tools** that aren't bound to a single migration epoch. It exists today
as a charter; its first inhabitants will land as the corresponding bug
classes or product needs surface.

What goes here
--------------

* ``revision_diff`` — diff between any two ``EventTypeRevision`` rows
  (by sequence or by date), surfaced as a structured change-set.
* ``revision_restore`` — restore an ``EventType.schema`` to a prior
  revision's snapshot. Non-destructive: writes a *new* revision rather
  than rewriting history.
* ``revision_as_of`` — read-only "what did this schema look like on
  date *X* / at sequence *Y*". Powers debug tooling and customer-support
  flows.
* ``data_compat_projection`` — runtime helper that takes an event whose
  stored details reference fields no longer present in the current
  ``EventType.schema`` and produces a render-friendly projection so
  reports and UI keep displaying historical data.
* ``ad_hoc_repair`` — future bug-driven schema repairs that don't fit
  the V1→V2 pattern. Each instance lives as a focused module here, with
  a one-shot data migration as the typical first surface and (when
  warranted) an operator-driven follow-up surface.

What does NOT go here
---------------------

* The V1→V2 migration tooling and its V2-collection repair
  (``activity.schemas.migration``). That package is V1→V2-bounded; once
  the corpus is migrated cleanly its job is done.
* Runtime schema rendering (``activity.schemas.schema_rendering``).
* Schema validation / metaschema definitions
  (``activity.schemas.eventtype_meta_schemas``).
* Auto-generation utilities (``activity.schemas.auto_generate``).

Surfaces pattern
----------------

Each tool is implemented as a service object or pure function in this
package. **Surfaces** that expose the tool to humans are thin adapters
that call into the service:

* **REST** — DRF ``@action`` methods on ``EventTypesViewSet`` (mirrors
  the existing ``migrate``, ``retrieve_updates``, and
  ``retrieve_schema`` actions).
* **Management commands** — under
  ``activity/management/commands/`` (one file per tool, named for the
  tool, mirrors the REST surface where possible).

The service layer is the single source of truth; surfaces stay light.
This mirrors the precedent set by ``MigrationService`` (in
``activity.schemas.migration.service``) ↔ ``migrate`` action on
``EventTypesViewSet``.

See ``docs/architecture/schema-ops.md`` for the full charter, decision
log, and open questions for whoever brings the next tool online.
"""
