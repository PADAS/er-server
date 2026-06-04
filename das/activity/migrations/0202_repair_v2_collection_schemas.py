"""Data migration: repair V2 EventType schemas damaged by the 0.1.3.x
migration tool's broken collection-field handling.

What it does
------------
For every V2 ``EventType`` across every tenant, walk the revision history
to classify it into one of the :class:`RepairStrategy` values:

* ``not_migrated``          — V2 since creation; nothing to fix.
* ``rebuild_from_v1``       — V1 is reconstructable from pre-migration
                              revisions; re-run ``transform_schema`` from
                              ``schema_migration_tool >= 0.1.4`` (which
                              has the collection bug fixed).
* ``reconstruct_from_json`` — V1 not reconstructable; hand the V2
                              schema to
                              ``schema_migration_tool.repair.repair_v2_schema``
                              (pinned at >=0.1.5 in ``pyproject.toml``),
                              which reconstructs ``ui.fields`` from the
                              JSON section using safe defaults. See
                              ``docs/architecture/v2-schema-repair-upstream-contract.md``.
* ``skip_user_edited``      — User has saved changes after migration;
                              skip to respect their edits.

Idempotency & safety
--------------------
The migration is idempotent by construction:

* ``rebuild_from_v1`` re-runs a deterministic transformation on the
  recovered V1.
* ``reconstruct_from_json``'s upstream ``repair_v2_schema`` returns
  ``was_modified=False`` on already-correct schemas (per the upstream
  contract).
* ``skip_user_edited`` / ``not_migrated`` are no-ops.

A broad ``try / except`` is wrapped around every single EventType so a
single corrupted row cannot block deploys across all environments. All
errors are logged with structured extras for Cloud Logging.

Reverse migration
-----------------
``noop`` — there is no meaningful undo. The repair only restores the
``ui.fields`` map to a structurally correct shape; the JSON payload
section (which contains the actual data shape contract) is unchanged.
Rolling back the migration would not undo the repaired UI without
re-introducing the bug.

Audit trail
-----------
Saving through the historical model does *not* fire ``RevisionMixin``
signals, so this migration intentionally does not append a revision row.
The full repair record lives in structured logs under the
``error_category=repair`` filter (see
``activity.schemas.migration.logger.ErrorCategory.REPAIR``).
"""

from __future__ import annotations

import logging

from django.db import migrations

# These imports are intentionally module-level. The repair package is
# pure Python — no Django model imports at top level — so there is no
# circular-import or app-loading concern.
from activity.schemas.migration.repair_apply import (
    APPLIED_REBUILT_FROM_V1,
    APPLIED_RECONSTRUCTED_FROM_JSON,
    REPAIR_V2_AVAILABLE,
    SKIPPED_ALREADY_CORRECT,
    SKIPPED_JSON_RECONSTRUCTION_DEFERRED,
    SKIPPED_NOT_MIGRATED,
    SKIPPED_USER_EDITED,
    TRANSFORM_AVAILABLE,
    attempt_repair,
)
from activity.schemas.ops.revision_history import fetch_in_migration
from core.models.core import DASTenant
from utils.tenant.managers import UnsetDASTenantContextManager

logger = logging.getLogger(__name__)


def _summary_log_extras(tenant_domain: str, counts: dict[str, int], error_count: int) -> dict:
    return {
        "error_category": "repair",
        # Raw-string label - the migration body uses Python's stdlib
        # logger (not MigrationLogger), so this is a free-form filter
        # token, not an ``ErrorCode`` value. Kept distinct from the
        # per-row ``repair_action.*`` labels so dashboards can pick out
        # the once-per-tenant marker.
        "error_code": "repair_tenant_summary",
        "tenant_name": tenant_domain,
        "repair_v2_available": REPAIR_V2_AVAILABLE,
        "transform_available": TRANSFORM_AVAILABLE,
        "counts_by_action": dict(counts),
        "error_count": error_count,
    }


def repair_v2_collection_schemas(apps, schema_editor):
    """Forward migration body — see module docstring."""

    EventType = apps.get_model("activity", "EventType")
    EventTypeRevision = apps.get_model("activity", "EventTypeRevision")
    db_alias = schema_editor.connection.alias

    # Match the pattern in activity/migrations/0198_fix_v2_link_fields: the
    # entire mutation block runs inside UnsetDASTenantContextManager so saves
    # bypass the tenant_field machinery on historical models. Per-tenant
    # iteration is preserved for structured logging only — queries are
    # explicitly scoped via filter(das_tenant=tenant) inside the unset context.
    with UnsetDASTenantContextManager():
        tenants = list(DASTenant.objects.using(db_alias).all())

    for tenant in tenants:
        tenant_domain = tenant.domain or str(tenant.id)
        counts: dict[str, int] = {}
        error_count = 0

        with UnsetDASTenantContextManager():
            # Use das_tenant_id (not das_tenant=tenant) because the historical
            # EventType model's FK rejects live DASTenant instances:
            #   ValueError: Cannot query "<domain>": Must be "DASTenant" instance.
            v2_event_types = list(
                EventType.objects.using(db_alias).filter(version="2", das_tenant_id=tenant.id).order_by("value")
            )

        for event_type in v2_event_types:
            try:
                history = fetch_in_migration(
                    event_type,
                    revision_model=EventTypeRevision,
                    db_alias=db_alias,
                    tenant_id=tenant.id,
                )
                outcome = attempt_repair(
                    history=history,
                    schema_text=event_type.schema or "",
                )

                counts[outcome.action] = counts.get(outcome.action, 0) + 1

                log_extras = {
                    "error_category": "repair",
                    "error_code": f"repair_action.{outcome.action}",
                    "tenant_name": tenant_domain,
                    "event_type": str(event_type.value),
                    "event_type_id": str(event_type.id),
                    "repair_strategy": outcome.classification.strategy.value,
                    "post_migration_schema_edits": (outcome.classification.post_migration_schema_edits),
                    "migration_revision_sequence": (outcome.classification.migration_revision_sequence or 0),
                    "metadata": outcome.metadata,
                }

                if outcome.action.startswith("error_"):
                    error_count += 1
                    logger.error(
                        "Repair error for EventType %s: %s",
                        event_type.value,
                        "; ".join(outcome.errors),
                        extra=log_extras,
                    )
                    continue

                if outcome.did_apply:
                    event_type.schema = outcome.new_schema_text
                    with UnsetDASTenantContextManager():
                        event_type.save(
                            using=db_alias,
                            update_fields=["schema", "updated_at"],
                        )
                    logger.info(
                        "Repaired V2 schema for EventType %s (%s)",
                        event_type.value,
                        outcome.action,
                        extra=log_extras,
                    )
                else:
                    # Skip — log at debug to avoid flooding deploys.
                    logger.debug(
                        "Skipped EventType %s (%s)",
                        event_type.value,
                        outcome.action,
                        extra=log_extras,
                    )
            except Exception:  # noqa: BLE001 — never let one row brick a deploy
                error_count += 1
                logger.exception(
                    "Unexpected error during repair for EventType %s; continuing.",
                    getattr(event_type, "value", "<unknown>"),
                    extra={
                        "error_category": "repair",
                        "error_code": "repair_action.error_unexpected",
                        "tenant_name": tenant_domain,
                        "event_type": str(getattr(event_type, "value", "")),
                        "event_type_id": str(getattr(event_type, "id", "")),
                    },
                )

        logger.info(
            "Repair run complete for tenant %s: %d processed, %d errors",
            tenant_domain,
            sum(counts.values()),
            error_count,
            extra=_summary_log_extras(tenant_domain, counts, error_count),
        )


# Used by tests as a stable reference point — keeps test imports stable
# even if the module is later renamed.
__all__ = [
    "repair_v2_collection_schemas",
    "APPLIED_REBUILT_FROM_V1",
    "APPLIED_RECONSTRUCTED_FROM_JSON",
    "SKIPPED_ALREADY_CORRECT",
    "SKIPPED_JSON_RECONSTRUCTION_DEFERRED",
    "SKIPPED_NOT_MIGRATED",
    "SKIPPED_USER_EDITED",
]


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0201_community_input"),
    ]

    operations = [
        migrations.RunPython(repair_v2_collection_schemas, migrations.RunPython.noop),
    ]
