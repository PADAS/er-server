# ADR: `activity/schemas/ops/` — namespace for schema lifecycle tools

> **Status:** Accepted (uninhabited)
> **Date:** 2026-05-11
> **Scope:** `das/activity/schemas/`

## Context

The DAS EventType schema is a long-lived, multi-revision artifact. It changes
shape over time (V1 → V2 migration, ad-hoc field edits, future migrations),
its history is captured per-revision via the `RevisionMixin`, and it is
referenced by event data that may outlive the schema version that wrote it.

Operating on this lifecycle is a recurring need:

* Bugs in migration tools recur. The V2 collection-field corruption
  (fixed by data migration `0202_repair_v2_collection_schemas`) is the
  most recent example; it will not be the last.
* Customer support periodically asks "what did this schema look like
  last Tuesday?" and "why did this old report stop displaying field X?".
* Reports built against historical events need to keep displaying data
  whose shape no longer matches the current schema.
* Operators occasionally need to roll back a misguided schema edit
  without losing the rest of the revision history.

Today, the only tooling that addresses any of this lives in
`activity/schemas/migration/` — a package whose name is accurate for the
V1 → V2 migration and the V2-collection repair (both V1 → V2-bounded
work) but would mislead a future engineer adding revision-diff or
restore tooling.

There is no agreed home for the broader class of tools, no precedent
file structure, and no documented pattern for surfacing them via REST
or management commands.

## Decision

Establish `activity/schemas/ops/` as the package home for
**revision-history-aware schema lifecycle tools that aren't bound to a
single migration epoch**.

The package is created in this PR with a charter `__init__.py` and zero
code. The first inhabitants will land when the corresponding bug
classes or product needs surface; this ADR documents the home and the
patterns so the next engineer doesn't re-invent them.

### Why a new sibling and not extending `migration/`

* The V2 collection repair *is* V1 → V2-bounded — it stays in
  `migration/` where it belongs.
* The future tools enumerated below are **not** V1 → V2-bounded. They
  apply to any schema, any revision, any tenant, indefinitely.
* The naming `migration/` would lie about scope. `ops/` accurately
  describes "operations on schemas in flight".

### Why now, when nothing inhabits it yet

* The repair work surfaced the question; the answer is fresher than it
  will ever be.
* An empty namespace with a charter is cheaper than a misplaced first
  inhabitant.
* Future PRs that add the first real tool can land smaller, focused
  diffs instead of bundling architecture decisions with code.

## Future tools (roadmap, not commitments)

The following are the candidate first inhabitants that surfaced during
the V2 repair work. Each represents a class of need; a real PR would
narrow scope, define the API, and land tests.

### `revision_diff`

Diff between any two `EventTypeRevision` rows, by `sequence` or by
date. Output is a structured change-set — added/removed/modified
fields, choice-list deltas, UI-only changes vs JSON-impacting
changes — usable by both human reviewers and automation.

**Why we'd want it:** debugging "what changed?" without forensic
diffing of two raw JSON blobs; building a UI-facing schema-history
view; surfacing change-of-contract events to alerting.

### `revision_restore`

Restore an `EventType.schema` to a prior revision's snapshot.
Non-destructive: writes a *new* revision rather than rewriting history.

**Why we'd want it:** "undo" for a misguided schema edit; rolling back
a bad bulk update; recovery from a future repair that does the wrong
thing.

### `revision_as_of`

Read-only "what did this schema look like on date *X* / at sequence
*Y*". Returns a reconstructed schema dict; does not mutate.

**Why we'd want it:** customer support; debug tooling; the foundation
that `revision_diff` and `revision_restore` build on; an answer to
"why did this report look different last month?".

### `data_compat_projection`

Runtime helper that takes an event whose `event_details` reference
fields no longer present in the current `EventType.schema` and
produces a render-friendly projection so reports and UI keep
displaying the historical data.

**Why we'd want it:** today, dropping a field from a schema silently
breaks display of every prior event that recorded that field. This is
*not* admin tooling — it's a runtime read-side concern that the
detail-view, list-view, and export paths would call.

> **Note:** this is the most architecturally unusual member of the
> roadmap. It may end up living in a different namespace if it grows
> into something the rendering pipeline owns. For now, the design
> question is captured here so it isn't lost.

### `ad_hoc_repair`

Future bug-driven schema repairs that don't fit the V1 → V2 pattern
(which has its own home in `migration/`). Each instance lives as a
focused module here.

**Pattern:** the typical first surface is a one-shot data migration
(like `0202_repair_v2_collection_schemas`) that calls the service.
When the bug class is open-ended or recurring, a management command
follows.

**Why we'd want it:** bugs recur. Having a defined home — and a
repeatable pattern — beats inventing one each time the next bug lands.

## Surfaces pattern

Each tool is implemented as a **service object or pure function** in
this package. **Surfaces** that expose the tool to humans are thin
adapters that call into the service:

```
                      activity/schemas/ops/<tool>_service.py
                                  ▲
                                  │  (call)
                ┌─────────────────┴──────────────────┐
                │                                    │
   activity/views/types_v2.py            activity/management/commands/
   (DRF @action on                       <tool>.py
   EventTypesViewSet)
   ↳ POST /v2/eventtypes/<tool>/         ↳ python manage.py <tool>
```

This mirrors the precedent set today by:

* `MigrationService` (in `activity/schemas/migration/service.py`)
* `migrate` action on `EventTypesViewSet` (in
  `activity/views/types_v2.py`) — calls `MigrationService.migrate()`.

The service layer is the single source of truth. Surfaces stay light
(serialization, authorization, output formatting). Tests primarily
target the service; surface tests cover wiring.

## Non-goals

The new namespace explicitly does **not**:

* Replace `activity/schemas/migration/`. V1 → V2 migration plus its
  V2-collection repair are V1 → V2-specific and stay there.
* Replace `activity/schemas/schema_rendering.py`. Runtime rendering of
  the *current* schema is its own concern.
* Replace `activity/schemas/eventtype_meta_schemas.py`. Validation /
  metaschema definitions are their own concern.
* Replace `activity/schemas/auto_generate.py`. Schema generation
  helpers are their own concern.
* Provide schema editing UX. That belongs to the existing
  serializers / viewsets, not to ops tooling.

## Open questions for the first inhabitant

The following decisions are deferred to the PR that lands the first
tool, captured here so they aren't re-discovered from scratch:

1. **Authentication / authorization.** Likely admin-only for the
   destructive tools (`revision_restore`, `ad_hoc_repair`); what about
   read-only ones (`revision_diff`, `revision_as_of`)? Reuse
   `EventCategoryPermissions` (per-category) or define a new
   ops-level permission class?
2. **Tenant isolation.** Existing patterns (`UnsetDASTenantContextManager`,
   `das_tenant_id` filtering) apply, but the ergonomics for
   single-tenant operator-driven runs need a clean answer.
3. **Audit trail.** Destructive tools should write a new
   `EventTypeRevision` (preserving history). The classifier in
   `activity/schemas/migration/repair.py` already understands the
   revision protocol — that pattern can be lifted.
4. **Idempotency.** The repair tooling is idempotent by construction;
   future tools should aim for the same so re-running is safe.
5. **Dry-run conventions.** `MigrationService` uses `dry_run` as a
   first-class parameter. New tools should match.
6. **Change-set format.** Whatever shape `revision_diff` settles on
   should be the lingua franca for `revision_restore` previews,
   `data_compat_projection` mappings, and operator output across the
   namespace.

## Status

* **Accepted** — namespace created with charter docstring; no
  inhabitants this PR.
* **Owner** — whoever lands the first real tool here owns the patterns
  this ADR sketches; updates to this ADR are expected and welcome.
* **First inhabitant** — TBD. The most likely candidates, in priority
  order, are: `revision_as_of` (foundational), `revision_diff`
  (consumer of the above), `data_compat_projection` (highest user
  value if/when an EventType edit silently breaks historical display),
  `ad_hoc_repair` (driven by whichever bug surfaces next).

## Appendix: existing schema-related packages

Quick map for newcomers:

| Path                                         | Purpose                                                |
| -------------------------------------------- | ------------------------------------------------------ |
| `activity/schemas/__init__.py`               | empty re-export point                                  |
| `activity/schemas/auto_generate.py`          | helpers for generating schemas from data shapes        |
| `activity/schemas/errors.py`                 | structured error types for schema operations           |
| `activity/schemas/eventtype_meta_schemas.py` | the V1 + V2 metaschemas; validation entry points       |
| `activity/schemas/eventtype_service.py`      | rendering + retrieval coordination                     |
| `activity/schemas/migration/`                | V1 → V2 migration tooling and the V2-collection repair |
| `activity/schemas/ops/`                      | **(this ADR)** revision-history-aware lifecycle tools  |
| `activity/schemas/schema_adapter.py`         | adapters between schema versions and consumers         |
| `activity/schemas/schema_rendering.py`       | runtime schema rendering for clients                   |
| `activity/schemas/schema_retrieving.py`      | schema lookup helpers                                  |
