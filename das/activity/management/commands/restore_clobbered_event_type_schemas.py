"""Restore ``activity_eventtype.schema`` values clobbered by data migration
``activity/migrations/0203_repair_v2_collection_schemas.py``.

The bug
-------
Migration 0203 walks V2 ``EventType`` rows per tenant and, for repaired rows,
calls::

    event_type.save(using=db_alias, update_fields=["schema", "updated_at"])

inside ``UnsetDASTenantContextManager`` (0203 lines 169-175).

``EventType.id`` is declared ``models.UUIDField(primary_key=True)``, but the
*same UUID is reused across tenants* for seeded / global event types. In
production the cluster is Citus-distributed and the physical primary key is the
composite ``(das_tenant_id, id)``. Because the save ran with the tenant context
unset, django-multitenant emitted::

    UPDATE activity_eventtype SET schema = …, updated_at = … WHERE id = <uuid>

with **no tenant predicate**. Every tenant's row sharing that UUID was therefore
overwritten with one tenant's repaired schema. Collateral damage includes V1
rows that share a UUID with a repaired V2 row: they kept ``version = '1'`` but
received a V2 schema body.

Only ``id`` values that exist under more than one tenant were ever at risk.
A non-shared ``id`` matched exactly one physical row, so its schema is correct
and is **never** touched by this command.

The fix
-------
This command restores the pre-migration schema for every backup row whose ``id``
is shared across tenants, keyed on the **composite** ``(id, das_tenant_id)``.

Hard requirements (each is load-bearing — do not relax):

* The ``WHERE`` clause always includes ``das_tenant_id`` (the Citus distribution
  column). This is simultaneously the bug fix (it pins the update to one
  tenant's physical row) and a Citus routing requirement. There is **no** code
  path in this command that updates by ``id`` alone.
* Every emitted statement (UPDATE and dry-run count) is confined to a **single**
  ``das_tenant_id``. A multi-tenant ``UPDATE … FROM (VALUES …)`` would touch
  several shards while joining a local intermediate, which the Citus planner can
  reject; grouping rows per tenant keeps each statement single-shard /
  router-executable. (The composite ``WHERE`` is still per-row and remains the
  correctness guarantee — the single-tenant grouping is purely a Citus
  execution concern.)
* ``schema IS DISTINCT FROM`` the backup value guards every write, so the
  command is idempotent and a no-op for any row the migration never actually
  changed.
* ``updated_at = now()`` is set intentionally — we do **not** restore the
  backup's ``updated_at``. Bumping it re-propagates the corrected row through
  CDC / the data warehouse.
* Writes go through raw SQL (``django.db.connection``), never the ORM
  ``save()``. Raw SQL is not tenant-scoped and does not fire ``RevisionMixin``
  signals — both intentional, mirroring 0203's no-revision behaviour. No
  ``UnsetDASTenantContextManager`` is needed for raw SQL.

Reversibility — auto-snapshot
-----------------------------
Before any ``--commit`` write, the command takes a full in-database snapshot of
``activity_eventtype``::

    CREATE TABLE activity_eventtype_bak_<UTC-timestamp> AS SELECT * FROM activity_eventtype;

The snapshot is created and **committed in its own statement before** the
restore transaction begins — mixing the ``CREATE TABLE AS`` DDL into the same
``transaction.atomic()`` as the per-shard writes is unsafe on Citus. Override
the name with ``--snapshot-table``; an existing name aborts. The snapshot name
is printed prominently after creation.

To roll back, replay the snapshot by composite key (restoring the original
``updated_at`` too)::

    UPDATE activity_eventtype t
    SET schema = b.schema, updated_at = b.updated_at
    FROM activity_eventtype_bak_<UTC-timestamp> b
    WHERE t.id = b.id AND t.das_tenant_id = b.das_tenant_id;

Once satisfied, ``DROP TABLE activity_eventtype_bak_<UTC-timestamp>;`` reclaims
the space. For off-box durability you may additionally dump the table before the
run::

    pg_dump -t activity_eventtype <conn-opts> > activity_eventtype_<cluster>_<ts>.sql
    # or, inside psql:  \copy activity_eventtype TO 'activity_eventtype_<cluster>_<ts>.csv' CSV HEADER

The backup CSV is a full dump of ``activity_eventtype`` taken **before** 0203
ran (confirmed pre-migration and clean). Each cluster has its own dump and the
matching CSV must be used against the matching cluster:

* er-prod      -> ``activity_eventtype_prod.csv``
* er-prod-us   -> ``activity_eventtype_prod_us.csv``

Using the wrong cluster's CSV would restore foreign data; the wrong-backup
safety check (step 5 below) aborts when too few of the CSV's tenant ids exist in
the target database.

Migration-window guard (``--modified-between``)
-----------------------------------------------
Optional. When supplied, the restore is additionally restricted to live rows
whose ``updated_at`` falls in the half-open interval ``[START, END)`` — layered
on top of the shared-id and ``schema IS DISTINCT FROM`` filters. Both bounds
must be timezone-aware ISO-8601 timestamps (an explicit offset is required; a
naive value aborts).

This pins the restore to rows the migration actually wrote and leaves
post-migration user edits untouched. For this incident, the clobbered rows
cluster on the migration day (2026-06-29) while a handful of legitimate edits
landed on 2026-06-30; the window below restores only the former::

    python manage.py restore_clobbered_event_type_schemas /tmp/backup.csv \
        --modified-between '2026-06-29 00:00:00+00:00' '2026-06-30 00:00:00+00:00' --commit

Rows edited after the window are deliberately out of scope here and must be
reconciled separately.

Usage
-----
Dry-run is the default; ``--commit`` is required to write.

    python manage.py restore_clobbered_event_type_schemas <backup_csv_path> \
        [--commit] [--batch-size 500] [--modified-between START END]

Operational runbook (copy the per-cluster backup into the pod, dry-run, review,
then re-run with ``--commit``)::

    # er-prod (use the matching CSV!)
    kubectl cp activity_eventtype_prod.csv <namespace>/<api-pod>:/tmp/backup.csv

    # 1. Dry-run — reports what WOULD change, writes nothing.
    kubectl exec -it <api-pod> -n <namespace> -- \
        python manage.py restore_clobbered_event_type_schemas /tmp/backup.csv

    # 2. (Optional) off-box durability dump before committing.
    kubectl exec -it <api-pod> -n <namespace> -- \
        bash -c "pg_dump -t activity_eventtype \"$DATABASE_URL\" > /tmp/activity_eventtype_prod_$(date -u +%Y%m%d_%H%M%S).sql"

    # 3. Review the dry-run output (overlap check, target counts, sample rows),
    #    then commit. --commit auto-snapshots the table first and prints the
    #    snapshot name; note it down for the rollback recipe above.
    kubectl exec -it <api-pod> -n <namespace> -- \
        python manage.py restore_clobbered_event_type_schemas /tmp/backup.csv --commit
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

# CSV schema text may carry embedded newlines / quotes; bump the field size cap
# so the stdlib csv reader does not choke on large schema bodies.
csv.field_size_limit(10**9)

DEFAULT_BATCH_SIZE = 500
# Abort if more than this fraction of the target set's tenant ids are absent
# from the database — almost certainly the wrong cluster's CSV.
MAX_MISSING_TENANT_FRACTION = 0.20

# Column order of the backup CSV (header present). We only consume id,
# das_tenant_id, schema, version and value; the rest are ignored.
EXPECTED_COLUMNS = [
    "id",
    "created_at",
    "updated_at",
    "value",
    "display",
    "ordernum",
    "schema",
    "category_id",
    "is_collection",
    "default_priority",
    "icon",
    "default_state",
    "auto_resolve",
    "resolve_time",
    "is_active",
    "geometry_type",
    "das_tenant_id",
    "version",
    "readonly",
]


@dataclass(frozen=True)
class BackupRow:
    """One backup row, narrowed to the fields this command cares about."""

    id: str
    das_tenant_id: str
    schema: str
    version: str
    value: str


@dataclass
class ParsedBackup:
    """Result of parsing the backup CSV and selecting target rows."""

    total_rows: int
    shared_ids: set[str]
    target_rows: list[BackupRow] = field(default_factory=list)

    @property
    def target_tenant_ids(self) -> set[str]:
        return {row.das_tenant_id for row in self.target_rows}

    def target_version_breakdown(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.target_rows:
            counts[row.version] = counts.get(row.version, 0) + 1
        return counts


def parse_backup_rows(reader: Iterable[dict[str, str]]) -> list[BackupRow]:
    """Read the narrowed fields out of a csv.DictReader-like iterable."""
    rows: list[BackupRow] = []
    for record in reader:
        rows.append(
            BackupRow(
                id=record["id"],
                das_tenant_id=record["das_tenant_id"],
                schema=record["schema"],
                version=record["version"],
                value=record["value"],
            )
        )
    return rows


def find_shared_ids(rows: Iterable[BackupRow]) -> set[str]:
    """Return every ``id`` that appears under more than one distinct tenant.

    These are the only ids the 0203 tenant-blind UPDATE could have clobbered.
    """
    tenants_by_id: dict[str, set[str]] = {}
    for row in rows:
        tenants_by_id.setdefault(row.id, set()).add(row.das_tenant_id)
    return {row_id for row_id, tenants in tenants_by_id.items() if len(tenants) > 1}


def select_target_rows(rows: list[BackupRow], shared_ids: set[str]) -> list[BackupRow]:
    """Every backup row whose id is shared across tenants is a restore target."""
    return [row for row in rows if row.id in shared_ids]


def build_backup(rows: list[BackupRow]) -> ParsedBackup:
    """Assemble the ParsedBackup (shared-id detection + target selection)."""
    shared_ids = find_shared_ids(rows)
    target_rows = select_target_rows(rows, shared_ids)
    return ParsedBackup(total_rows=len(rows), shared_ids=shared_ids, target_rows=target_rows)


def iter_tenant_batches(rows: list[BackupRow], batch_size: int) -> Iterator[list[BackupRow]]:
    """Yield single-tenant batches of at most ``batch_size`` rows.

    Rows are first grouped by ``das_tenant_id`` (so no yielded batch ever mixes
    tenants — required for Citus single-shard / router execution), then each
    tenant's rows are chunked by ``batch_size``. The union of all yielded
    batches equals the input ``rows``.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    by_tenant: dict[str, list[BackupRow]] = {}
    for row in rows:
        by_tenant.setdefault(row.das_tenant_id, []).append(row)
    for tenant_rows in by_tenant.values():
        for start in range(0, len(tenant_rows), batch_size):
            yield tenant_rows[start : start + batch_size]


def build_update_sql(
    batch: list[BackupRow],
    window: tuple[datetime, datetime] | None = None,
) -> tuple[str, list[object]]:
    """Build the composite-key restore UPDATE for one single-tenant batch.

    The VALUES list carries ``(id, das_tenant_id, schema)`` per row and the join
    predicate matches on **both** ``id`` and ``das_tenant_id``. ``IS DISTINCT
    FROM`` skips rows whose live schema already equals the backup, making the
    statement idempotent. There is deliberately no id-only path. ``RETURNING``
    surfaces the rows actually changed so the caller can sample them for audit.

    When ``window`` (``[start, end)``) is given, an additional
    ``t.updated_at >= %s AND t.updated_at < %s`` predicate restricts the restore
    to rows touched within that half-open interval (so post-migration user edits
    are left untouched). When it is ``None`` the SQL is unchanged.
    """
    placeholders = ", ".join(["(%s::uuid, %s::uuid, %s::text)"] * len(batch))
    sql = (
        "UPDATE activity_eventtype AS t "
        "SET schema = v.schema, updated_at = now() "
        f"FROM (VALUES {placeholders}) AS v(id, das_tenant_id, schema) "
        "WHERE t.id = v.id AND t.das_tenant_id = v.das_tenant_id "
        "AND t.schema IS DISTINCT FROM v.schema"
    )
    params: list[object] = []
    for row in batch:
        params.extend([row.id, row.das_tenant_id, row.schema])
    if window is not None:
        sql += " AND t.updated_at >= %s AND t.updated_at < %s"
        params.extend([window[0], window[1]])
    sql += " RETURNING t.value, t.id, t.das_tenant_id"
    return sql, params


def build_count_sql(
    batch: list[BackupRow],
    window: tuple[datetime, datetime] | None = None,
) -> tuple[str, list[object]]:
    """Build the dry-run query for one single-tenant batch (same join + guard).

    Returns the ``(value, id, das_tenant_id)`` of every row that WOULD change,
    so the caller can both count and sample them. Honours the optional
    ``window`` exactly as ``build_update_sql`` does.
    """
    placeholders = ", ".join(["(%s::uuid, %s::uuid, %s::text)"] * len(batch))
    sql = (
        "SELECT t.value, t.id, t.das_tenant_id "
        "FROM activity_eventtype AS t "
        f"JOIN (VALUES {placeholders}) AS v(id, das_tenant_id, schema) "
        "ON t.id = v.id AND t.das_tenant_id = v.das_tenant_id "
        "WHERE t.schema IS DISTINCT FROM v.schema"
    )
    params: list[object] = []
    for row in batch:
        params.extend([row.id, row.das_tenant_id, row.schema])
    if window is not None:
        sql += " AND t.updated_at >= %s AND t.updated_at < %s"
        params.extend([window[0], window[1]])
    return sql, params


def count_existing_tenant_ids(tenant_ids: set[str]) -> int:
    """How many of ``tenant_ids`` actually exist in activity_eventtype.

    Used by the wrong-backup safety check. Querying activity_eventtype (rather
    than core DASTenant) keeps the check on the same table we are about to
    modify and avoids cross-app raw joins.
    """
    if not tenant_ids:
        return 0
    ids = list(tenant_ids)
    placeholders = ", ".join(["%s::uuid"] * len(ids))
    sql = "SELECT count(DISTINCT das_tenant_id) " "FROM activity_eventtype " f"WHERE das_tenant_id IN ({placeholders})"
    with connection.cursor() as cur:
        cur.execute(sql, ids)
        row = cur.fetchone()
    return int(row[0]) if row else 0


def parse_modified_window(values: list[str]) -> tuple[datetime, datetime]:
    """Parse ``--modified-between START END`` into aware ``(start, end)``.

    Both values must be ISO-8601 with an explicit offset. A value that fails to
    parse, or that parses to a naive datetime, raises ``CommandError`` — a naive
    bound would compare ambiguously against the tz-aware ``updated_at`` column.
    """
    start_raw, end_raw = values
    parsed: list[datetime] = []
    for label, raw in (("START", start_raw), ("END", end_raw)):
        dt = parse_datetime(raw)
        if dt is None:
            raise CommandError(
                f"--modified-between {label} value {raw!r} is not a valid ISO-8601 timestamp. "
                "Use an explicit offset, e.g. '2026-06-29 00:00:00+00:00'."
            )
        if dt.tzinfo is None:
            raise CommandError(
                f"--modified-between {label} value {raw!r} is timezone-naive. "
                "Provide an explicit offset, e.g. '2026-06-29 00:00:00+00:00'."
            )
        parsed.append(dt)
    return parsed[0], parsed[1]


# Snapshot table names are interpolated into DDL (cannot be parameterized), so
# they are restricted to a safe identifier shape to prevent SQL injection.
_SNAPSHOT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_snapshot_name(now: datetime | None = None) -> str:
    """``activity_eventtype_bak_<UTC-timestamp>`` (e.g. ``..._20260630_141500``)."""
    stamp = (now or datetime.now(tz=timezone.utc)).strftime("%Y%m%d_%H%M%S")
    return f"activity_eventtype_bak_{stamp}"


def snapshot_table_exists(name: str) -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", [name])
        row = cur.fetchone()
    return bool(row and row[0] is not None)


def create_snapshot(name: str) -> None:
    """Create a full copy of activity_eventtype in its own committed statement.

    The DDL must NOT run inside the restore's ``transaction.atomic()`` (mixing
    DDL with the per-shard writes is unsafe on Citus); callers invoke this before
    opening the restore transaction. The name is validated against
    ``_SNAPSHOT_NAME_RE`` because it cannot be parameterized in DDL.
    """
    if not _SNAPSHOT_NAME_RE.match(name):
        raise CommandError(f"Invalid snapshot table name {name!r}: must match [A-Za-z_][A-Za-z0-9_]*.")
    if snapshot_table_exists(name):
        raise CommandError(f"Snapshot table {name!r} already exists. Choose another --snapshot-table or drop it.")
    with connection.cursor() as cur:
        cur.execute(f'CREATE TABLE "{name}" AS SELECT * FROM activity_eventtype')


class Command(BaseCommand):
    help = (
        "Restore activity_eventtype.schema values clobbered by migration 0203 "
        "(the tenant-blind UPDATE that overwrote every tenant's row sharing a "
        "UUID). Restores by composite (id, das_tenant_id) key from a pre-0203 "
        "backup CSV. Dry-run by default; pass --commit to write. Deliberately "
        "cross-tenant (no TenantCommandMixin)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "backup_csv_path",
            type=Path,
            help="Path to the pre-0203 activity_eventtype backup CSV (must match the target cluster).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Perform the UPDATEs inside a single transaction. Without this flag the command is a dry-run.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Rows per single-tenant batch (default {DEFAULT_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--snapshot-table",
            type=str,
            default=None,
            help=(
                "Name of the pre-write snapshot table. Defaults to "
                "activity_eventtype_bak_<UTC-timestamp>. Aborts if it already exists. "
                "Only used with --commit."
            ),
        )
        parser.add_argument(
            "--modified-between",
            nargs=2,
            metavar=("START", "END"),
            default=None,
            help=(
                "Restrict the restore to live rows whose updated_at falls in the half-open "
                "interval [START, END). Both must be timezone-aware ISO-8601 timestamps "
                "(e.g. '2026-06-29 00:00:00+00:00'). Use this to target only rows the migration "
                "actually wrote and skip post-migration user edits."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        backup_csv_path: Path = options["backup_csv_path"]  # type: ignore[assignment]
        commit: bool = bool(options["commit"])
        batch_size: int = int(options["batch_size"])  # type: ignore[arg-type]
        snapshot_table: str | None = options["snapshot_table"]  # type: ignore[assignment]
        modified_between: list[str] | None = options["modified_between"]  # type: ignore[assignment]

        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1.")
        if not backup_csv_path.exists():
            raise CommandError(f"Backup CSV not found: {backup_csv_path}")

        window = parse_modified_window(modified_between) if modified_between else None

        backup = self._parse(backup_csv_path)
        self._report_parse(backup)

        if not backup.target_rows:
            self.stdout.write(self.style.SUCCESS("No shared ids in the backup — nothing to restore."))
            return

        self._safety_check(backup)

        if window is not None:
            self.stdout.write(f"Restricting to rows modified in [{window[0].isoformat()}, {window[1].isoformat()}).")

        if commit:
            self._commit(backup, batch_size, snapshot_table, window)
        else:
            self._dry_run(backup, batch_size, window)

    def _parse(self, backup_csv_path: Path) -> ParsedBackup:
        with backup_csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = [col for col in EXPECTED_COLUMNS if col not in (reader.fieldnames or [])]
            if missing:
                raise CommandError(
                    f"Backup CSV is missing expected column(s): {', '.join(missing)}. "
                    "Is this an activity_eventtype dump?"
                )
            rows = parse_backup_rows(reader)
        return build_backup(rows)

    def _report_parse(self, backup: ParsedBackup) -> None:
        self.stdout.write(f"Parsed {backup.total_rows} backup row(s).")
        self.stdout.write(
            f"Shared ids (present in >1 tenant): {len(backup.shared_ids)}; "
            f"target rows (rows with a shared id): {len(backup.target_rows)}."
        )
        breakdown = backup.target_version_breakdown()
        v1 = breakdown.get("1", 0)
        v2 = breakdown.get("2", 0)
        other = sum(count for ver, count in breakdown.items() if ver not in ("1", "2"))
        msg = f"Target rows by version: v1={v1}, v2={v2}"
        if other:
            msg += f", other={other}"
        self.stdout.write(msg)
        logger.info(
            "restore_clobbered_event_type_schemas parsed backup",
            extra={
                "total_rows": backup.total_rows,
                "shared_ids": len(backup.shared_ids),
                "target_rows": len(backup.target_rows),
                "version_breakdown": breakdown,
            },
        )

    def _safety_check(self, backup: ParsedBackup) -> None:
        target_tenant_ids = backup.target_tenant_ids
        present = count_existing_tenant_ids(target_tenant_ids)
        total = len(target_tenant_ids)
        missing = total - present
        missing_fraction = missing / total if total else 0.0

        self.stdout.write(
            f"Tenant overlap: {present}/{total} target tenant id(s) present in activity_eventtype "
            f"({missing} missing, {missing_fraction:.0%})."
        )
        logger.info(
            "restore_clobbered_event_type_schemas tenant overlap",
            extra={
                "target_tenant_ids": total,
                "present_tenant_ids": present,
                "missing_tenant_ids": missing,
                "missing_fraction": missing_fraction,
            },
        )
        if missing_fraction > MAX_MISSING_TENANT_FRACTION:
            raise CommandError(
                f"{missing}/{total} ({missing_fraction:.0%}) of target tenant ids are absent from this database, "
                f"exceeding the {MAX_MISSING_TENANT_FRACTION:.0%} threshold. This is almost certainly the wrong "
                "cluster's backup CSV (er-prod uses activity_eventtype_prod.csv; er-prod-us uses "
                "activity_eventtype_prod_us.csv). Aborting."
            )

    def _dry_run(self, backup: ParsedBackup, batch_size: int, window: tuple[datetime, datetime] | None) -> None:
        would_change: list[tuple[str, str, str]] = []
        with connection.cursor() as cur:
            for batch in iter_tenant_batches(backup.target_rows, batch_size):
                sql, params = build_count_sql(batch, window)
                cur.execute(sql, params)
                would_change.extend((str(value), str(id_), str(tenant_id)) for value, id_, tenant_id in cur.fetchall())

        self.stdout.write(
            self.style.SUCCESS(f"[DRY-RUN] {len(would_change)} row(s) WOULD change. No writes performed.")
        )
        self._print_sample(would_change, "would change")
        logger.info(
            "restore_clobbered_event_type_schemas dry-run complete",
            extra={"would_change": len(would_change), "modified_window": self._window_extra(window)},
        )

    def _commit(
        self,
        backup: ParsedBackup,
        batch_size: int,
        snapshot_table: str | None,
        window: tuple[datetime, datetime] | None,
    ) -> None:
        # Snapshot first, in its own committed statement BEFORE the restore txn.
        snapshot_name = snapshot_table or default_snapshot_name()
        create_snapshot(snapshot_name)
        self.stdout.write(self.style.WARNING(f"Snapshot created: {snapshot_name} (full copy of activity_eventtype)."))
        self.stdout.write(
            self.style.WARNING("To roll back, replay this snapshot by composite key (see module docstring).")
        )
        logger.info(
            "restore_clobbered_event_type_schemas snapshot created",
            extra={"snapshot_table": snapshot_name},
        )

        changed: list[tuple[str, str, str]] = []
        with transaction.atomic():
            with connection.cursor() as cur:
                for batch in iter_tenant_batches(backup.target_rows, batch_size):
                    sql, params = build_update_sql(batch, window)
                    cur.execute(sql, params)
                    changed.extend((str(value), str(id_), str(tenant_id)) for value, id_, tenant_id in cur.fetchall())

        self.stdout.write(self.style.SUCCESS(f"Restored {len(changed)} row(s)."))
        self._print_sample(changed, "changed")
        logger.info(
            "restore_clobbered_event_type_schemas commit complete",
            extra={
                "changed": len(changed),
                "snapshot_table": snapshot_name,
                "modified_window": self._window_extra(window),
            },
        )

    @staticmethod
    def _window_extra(window: tuple[datetime, datetime] | None) -> list[str] | None:
        if window is None:
            return None
        return [window[0].isoformat(), window[1].isoformat()]

    def _print_sample(self, rows: list[tuple[str, str, str]], label: str) -> None:
        sample = rows[:20]
        if not sample:
            return
        self.stdout.write(f"Sample of rows {label} (showing {len(sample)} of {len(rows)}):")
        for value, id_, tenant_id in sample:
            self.stdout.write(f"  - {value} ({id_}, {tenant_id})")
