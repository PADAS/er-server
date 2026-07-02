"""Repair V2 EventType schemas damaged by the 0.1.3.x migration tool's broken
collection-field handling.

This command replicates the repair logic that was previously carried by the
``0203_repair_v2_collection_schemas`` data migration. That migration was
neutralized (ERA-13385/ERA-13535).
Running per tenant via this command keeps every write scoped to the active tenant.
Run it explicitly, once per tenant, to apply or re-inspect repairs.

What it does
------------
For every V2 ``EventType`` in the tenant, walk the revision history to
classify it into one of the :class:`~activity.schemas.migration.repair.RepairStrategy`
values and act accordingly:

* ``not_migrated``          — V2 since creation; nothing to fix.
* ``rebuild_from_v1``       — V1 is reconstructable from pre-migration
                              revisions; re-run ``transform_schema`` from
                              ``schema_migration_tool >= 0.1.4``.
* ``reconstruct_from_json`` — V1 not reconstructable; hand the V2 schema to
                              ``schema_migration_tool.repair.repair_v2_schema``
                              (pinned at ==0.1.5.2), which reconstructs
                              ``ui.fields`` from the JSON section using safe
                              defaults.
* ``skip_user_edited``      — User saved changes after migration; skipped to
                              respect their edits.

Audit trail
-----------
Unlike the data migration, this command saves through the live ``EventType``
model which fires ``RevisionMixin`` signals — each repair is recorded as a
standard revision row, giving a full audit trail.

Usage examples
--------------
    # Repair every V2 event type in a tenant
    python manage.py repair_v2_collection_schemas --all --tenant_domain <domain>

    # Preview without writing
    python manage.py repair_v2_collection_schemas --all --tenant_domain <domain> --dry-run

    # Target specific event types
    python manage.py repair_v2_collection_schemas sgrc_carcass wildlife_patrol \\
        --tenant_domain <domain>
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from activity.models import EventType
from activity.schemas.migration.repair_apply import SKIPPED_NEEDS_REVIEW, attempt_repair
from activity.schemas.ops.revision_history import fetch
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Repair V2 EventType schemas damaged by the 0.1.3.x migration tool's broken "
        "collection-field handling. Scoped to the tenant given by --tenant_domain."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "values",
            nargs="*",
            help="Event type value(s) to repair. Omit only when using --all.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="repair_all",
            help="Repair every V2 event type in the tenant.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options) -> None:
        values: list[str] = options["values"]
        repair_all: bool = options["repair_all"]
        dry_run: bool = options["dry_run"]
        verbosity: int = options.get("verbosity", 1)

        if not values and not repair_all:
            raise CommandError("Specify one or more event type values, or pass --all.")
        if values and repair_all:
            raise CommandError("Pass either explicit event type values or --all, not both.")

        qs = EventType.objects.filter(version=EventType.VersionChoices.VERSION_2)
        if values:
            qs = qs.filter(value__in=values)

        counts: dict[str, int] = {}
        error_count = 0
        found: set[str] = set()

        for event_type in qs.order_by("value"):
            found.add(event_type.value)
            try:
                history = fetch(event_type)
                outcome = attempt_repair(
                    history=history,
                    schema_text=event_type.schema or "",
                )

                counts[outcome.action] = counts.get(outcome.action, 0) + 1

                log_extras = {
                    "error_category": "repair",
                    "error_code": f"repair_action.{outcome.action}",
                    "event_type": str(event_type.value),
                    "event_type_id": str(event_type.id),
                    "repair_strategy": outcome.classification.strategy.value,
                    "post_migration_schema_edits": outcome.classification.post_migration_schema_edits,
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
                    self.stderr.write(
                        f"  ! {event_type.value}: repair error ({outcome.action}): " + "; ".join(outcome.errors)
                    )
                    continue

                if outcome.did_apply:
                    if dry_run:
                        self.stdout.write(f"  * {event_type.value}: would apply ({outcome.action})")
                    else:
                        event_type.schema = outcome.new_schema_text
                        event_type.updated_at = timezone.now()
                        event_type.save(update_fields=["schema", "updated_at"])
                        logger.info(
                            "Repaired V2 schema for EventType %s (%s)",
                            event_type.value,
                            outcome.action,
                            extra=log_extras,
                        )
                        self.stdout.write(f"  * {event_type.value}: repaired ({outcome.action})")
                elif outcome.action == SKIPPED_NEEDS_REVIEW:
                    # Diagnostics present — corruption beyond the collection-key
                    # bug that the repair tool won't auto-fix. Warn so operators
                    # can build a manual-review queue; metadata carries the
                    # diagnostic change summary.
                    logger.warning(
                        "EventType %s needs manual review (%s)",
                        event_type.value,
                        outcome.action,
                        extra=log_extras,
                    )
                    self.stderr.write(
                        f"  ? {event_type.value}: needs manual review ({outcome.action}) "
                        f"— upstream_changes={outcome.metadata.get('upstream_changes', '?')}, "
                        f"summary={outcome.metadata.get('upstream_change_summary', [])}"
                    )
                else:
                    # Other skips (already_correct, not_migrated, user_edited) —
                    # only print at verbosity >= 2 to avoid flooding output.
                    logger.debug(
                        "Skipped EventType %s (%s)",
                        event_type.value,
                        outcome.action,
                        extra=log_extras,
                    )
                    if verbosity >= 2:
                        self.stdout.write(f"  - {event_type.value}: skipped ({outcome.action})")

            except ValidationError as exc:
                # EventType.save() runs full_clean() on every save, including
                # partial update_fields saves. A legacy/damaged row with an
                # unrelated invalid field (over-length icon, out-of-range
                # resolve_time, …) fails validation here rather than being
                # repaired. Bucket it distinctly from truly unexpected errors so
                # the failure cause is not lost, and continue to the next row.
                error_count += 1
                counts["error_validation"] = counts.get("error_validation", 0) + 1
                messages = "; ".join(exc.messages)
                logger.error(
                    "EventType %s failed model validation on save; not repaired. Continuing. %s",
                    event_type.value,
                    messages,
                    extra={
                        "error_category": "repair",
                        "error_code": "repair_action.error_validation",
                        "event_type": str(event_type.value),
                        "event_type_id": str(event_type.id),
                    },
                )
                self.stderr.write(f"  ! {event_type.value}: validation error (not repaired): {messages}")

            except Exception:  # noqa: BLE001 — never let one row abort the run
                error_count += 1
                logger.exception(
                    "Unexpected error during repair for EventType %s; continuing.",
                    getattr(event_type, "value", "<unknown>"),
                    extra={
                        "error_category": "repair",
                        "error_code": "repair_action.error_unexpected",
                        "event_type": str(getattr(event_type, "value", "")),
                        "event_type_id": str(getattr(event_type, "id", "")),
                    },
                )
                self.stderr.write(f"  ! {getattr(event_type, 'value', '<unknown>')}: unexpected error (see logs)")

        if values:
            for missing in sorted(set(values) - found):
                self.stderr.write(f"  ! no V2 event type found with value '{missing}'")

        total = sum(counts.values())
        verb = "Would apply" if dry_run else "Applied"
        logger.info(
            "Repair run complete: %d processed, %d errors",
            total,
            error_count,
            extra={
                "error_category": "repair",
                "error_code": "repair_tenant_summary",
                "counts_by_action": dict(counts),
                "error_count": error_count,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {verb} repairs to {total} event type(s). "
                f"Counts by action: {counts}. "
                f"Errors: {error_count}."
            )
        )
