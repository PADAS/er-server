"""Tests for the ``restore_clobbered_event_type_schemas`` management command.

Test-environment constraint
---------------------------
The test Postgres is NOT Citus, so ``activity_eventtype.id`` is a true unique
primary key — we cannot insert two rows sharing an ``id`` under different
tenants. Therefore:

* The *pure logic* (CSV parsing, shared-id detection, target selection,
  VALUES-batch / SQL construction) is unit-tested directly against in-memory
  data, with no DB. Duplicate-id-across-tenants scenarios live only here.
* The *DB write path* is integration-tested with **distinct** ids across two
  tenants (composite key still exercised; only the physical PK collision is
  impossible to reproduce off-Citus).
"""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from activity.management.commands import restore_clobbered_event_type_schemas as cmd
from factories import TenantFactory


def _csv_record(
    *,
    id: str,
    das_tenant_id: str,
    schema: str,
    version: str = "2",
    value: str = "carcass_rep",
) -> dict[str, str]:
    return {
        "id": id,
        "created_at": "2026-01-01 00:00:00+00",
        "updated_at": "2026-01-01 00:00:00+00",
        "value": value,
        "display": value.title(),
        "ordernum": "1",
        "schema": schema,
        "category_id": str(uuid.uuid4()),
        "is_collection": "f",
        "default_priority": "0",
        "icon": "",
        "default_state": "new",
        "auto_resolve": "f",
        "resolve_time": "",
        "is_active": "t",
        "geometry_type": "Point",
        "das_tenant_id": das_tenant_id,
        "version": version,
        "readonly": "f",
    }


def _write_csv(path, records: list[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cmd.EXPECTED_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(record)


class TestSharedIdDetection:
    def test_id_under_two_tenants_is_shared(self) -> None:
        shared_uuid = str(uuid.uuid4())
        rows = [
            cmd.BackupRow(id=shared_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a"),
            cmd.BackupRow(id=shared_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="1", value="a"),
        ]
        assert cmd.find_shared_ids(rows) == {shared_uuid}

    def test_id_under_one_tenant_is_not_shared(self) -> None:
        only_id = str(uuid.uuid4())
        tenant = str(uuid.uuid4())
        rows = [
            cmd.BackupRow(id=only_id, das_tenant_id=tenant, schema="{}", version="2", value="a"),
        ]
        assert cmd.find_shared_ids(rows) == set()

    def test_same_id_same_tenant_twice_is_not_shared(self) -> None:
        only_id = str(uuid.uuid4())
        tenant = str(uuid.uuid4())
        rows = [
            cmd.BackupRow(id=only_id, das_tenant_id=tenant, schema="{}", version="2", value="a"),
            cmd.BackupRow(id=only_id, das_tenant_id=tenant, schema="{}", version="2", value="a"),
        ]
        assert cmd.find_shared_ids(rows) == set()

    def test_target_selection_keeps_only_shared_id_rows(self) -> None:
        shared_uuid = str(uuid.uuid4())
        lonely_uuid = str(uuid.uuid4())
        rows = [
            cmd.BackupRow(id=shared_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="shared"),
            cmd.BackupRow(id=shared_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="1", value="shared"),
            cmd.BackupRow(id=lonely_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="lonely"),
        ]
        backup = cmd.build_backup(rows)
        assert {r.value for r in backup.target_rows} == {"shared"}
        assert all(r.id == shared_uuid for r in backup.target_rows)
        assert len(backup.target_rows) == 2

    def test_version_breakdown_counts_v1_and_v2_targets(self) -> None:
        shared_uuid = str(uuid.uuid4())
        rows = [
            cmd.BackupRow(id=shared_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a"),
            cmd.BackupRow(id=shared_uuid, das_tenant_id=str(uuid.uuid4()), schema="{}", version="1", value="a"),
        ]
        backup = cmd.build_backup(rows)
        assert backup.target_version_breakdown() == {"2": 1, "1": 1}


class TestCsvParsing:
    def test_parses_narrowed_fields(self) -> None:
        rec_id = str(uuid.uuid4())
        tenant = str(uuid.uuid4())
        records = [_csv_record(id=rec_id, das_tenant_id=tenant, schema='{"json": {}}', version="2", value="x")]
        rows = cmd.parse_backup_rows(records)
        assert rows == [cmd.BackupRow(id=rec_id, das_tenant_id=tenant, schema='{"json": {}}', version="2", value="x")]

    def test_schema_with_embedded_newlines_and_quotes_round_trips(self, tmp_path) -> None:
        gnarly = '{"json": {\n  "title": "a \\"quoted\\" value",\n  "x": 1\n}}'
        rec_id = str(uuid.uuid4())
        tenant = str(uuid.uuid4())
        path = tmp_path / "backup.csv"
        _write_csv(path, [_csv_record(id=rec_id, das_tenant_id=tenant, schema=gnarly)])
        with open(path, newline="", encoding="utf-8") as handle:
            rows = cmd.parse_backup_rows(csv.DictReader(handle))
        assert len(rows) == 1
        assert rows[0].schema == gnarly


class TestSqlConstruction:
    def test_update_sql_always_includes_das_tenant_id(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        sql, params = cmd.build_update_sql(rows)
        assert "das_tenant_id" in sql
        assert "t.id = v.id AND t.das_tenant_id = v.das_tenant_id" in sql
        assert "IS DISTINCT FROM" in sql
        assert "updated_at = now()" in sql
        assert "RETURNING t.value, t.id, t.das_tenant_id" in sql
        # id, das_tenant_id, schema per row
        assert params == [rows[0].id, rows[0].das_tenant_id, rows[0].schema]

    def test_update_sql_never_keys_on_id_alone(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        sql, _ = cmd.build_update_sql(rows)
        # The only WHERE join must require both columns; an id-only predicate
        # ("t.id = v.id" not immediately followed by the tenant clause) must not exist.
        assert "WHERE t.id = v.id AND t.das_tenant_id = v.das_tenant_id" in sql

    def test_count_sql_includes_das_tenant_id_and_guard(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        sql, params = cmd.build_count_sql(rows)
        assert "das_tenant_id" in sql
        assert "SELECT t.value, t.id, t.das_tenant_id" in sql
        assert "IS DISTINCT FROM" in sql
        assert params == [rows[0].id, rows[0].das_tenant_id, rows[0].schema]

    def test_batches_split_by_batch_size_within_one_tenant(self) -> None:
        tenant = str(uuid.uuid4())
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=tenant, schema="{}", version="2", value=f"v{i}")
            for i in range(5)
        ]
        batches = list(cmd.iter_tenant_batches(rows, batch_size=2))
        assert [len(b) for b in batches] == [2, 2, 1]

    def test_batch_params_have_three_per_row(self) -> None:
        rows = [
            cmd.BackupRow(
                id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value=f"v{i}"
            )
            for i in range(3)
        ]
        sql, params = cmd.build_update_sql(rows)
        assert sql.count("%s::uuid, %s::uuid, %s::text") == 3
        assert len(params) == 9

    def test_update_sql_omits_window_predicate_when_no_window(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        sql, params = cmd.build_update_sql(rows)
        assert "updated_at >=" not in sql
        assert len(params) == 3

    def test_update_sql_appends_window_predicate_and_two_params(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        start = datetime(2026, 6, 29, tzinfo=timezone.utc)
        end = datetime(2026, 6, 30, tzinfo=timezone.utc)
        sql, params = cmd.build_update_sql(rows, window=(start, end))
        assert "AND t.updated_at >= %s AND t.updated_at < %s" in sql
        # RETURNING must still trail the window predicate.
        assert sql.index("updated_at >=") < sql.index("RETURNING")
        assert params == [rows[0].id, rows[0].das_tenant_id, rows[0].schema, start, end]

    def test_count_sql_omits_window_predicate_when_no_window(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        sql, params = cmd.build_count_sql(rows)
        assert "updated_at >=" not in sql
        assert len(params) == 3

    def test_count_sql_appends_window_predicate_and_two_params(self) -> None:
        rows = [
            cmd.BackupRow(id=str(uuid.uuid4()), das_tenant_id=str(uuid.uuid4()), schema="{}", version="2", value="a")
        ]
        start = datetime(2026, 6, 29, tzinfo=timezone.utc)
        end = datetime(2026, 6, 30, tzinfo=timezone.utc)
        sql, params = cmd.build_count_sql(rows, window=(start, end))
        assert "AND t.updated_at >= %s AND t.updated_at < %s" in sql
        assert params == [rows[0].id, rows[0].das_tenant_id, rows[0].schema, start, end]


class TestParseModifiedWindow:
    def test_parses_aware_iso_timestamps(self) -> None:
        start, end = cmd.parse_modified_window(["2026-06-29 00:00:00+00:00", "2026-06-30 00:00:00+00:00"])
        assert start == datetime(2026, 6, 29, tzinfo=timezone.utc)
        assert end == datetime(2026, 6, 30, tzinfo=timezone.utc)

    def test_rejects_naive_start(self) -> None:
        with pytest.raises(CommandError, match="timezone-naive"):
            cmd.parse_modified_window(["2026-06-29 00:00:00", "2026-06-30 00:00:00+00:00"])

    def test_rejects_naive_end(self) -> None:
        with pytest.raises(CommandError, match="timezone-naive"):
            cmd.parse_modified_window(["2026-06-29 00:00:00+00:00", "2026-06-30 00:00:00"])

    def test_rejects_unparseable(self) -> None:
        with pytest.raises(CommandError, match="not a valid ISO-8601"):
            cmd.parse_modified_window(["not-a-date", "2026-06-30 00:00:00+00:00"])


class TestTenantBatching:
    def _rows(self, tenant_counts: dict[str, int]) -> list[cmd.BackupRow]:
        rows: list[cmd.BackupRow] = []
        for tenant, count in tenant_counts.items():
            for i in range(count):
                rows.append(
                    cmd.BackupRow(
                        id=str(uuid.uuid4()), das_tenant_id=tenant, schema="{}", version="2", value=f"{tenant}_{i}"
                    )
                )
        return rows

    def test_no_batch_mixes_tenants(self) -> None:
        t1, t2, t3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        rows = self._rows({t1: 7, t2: 3, t3: 5})
        for batch in cmd.iter_tenant_batches(rows, batch_size=2):
            tenant_ids = {row.das_tenant_id for row in batch}
            assert len(tenant_ids) == 1, f"batch mixed tenants: {tenant_ids}"

    def test_union_of_batches_equals_target_set(self) -> None:
        t1, t2, t3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        rows = self._rows({t1: 7, t2: 3, t3: 5})
        collected: list[cmd.BackupRow] = []
        for batch in cmd.iter_tenant_batches(rows, batch_size=2):
            collected.extend(batch)
        # Same multiset of rows (order may differ because rows are grouped).
        key = lambda r: (r.das_tenant_id, r.value)
        assert sorted(collected, key=key) == sorted(rows, key=key)

    def test_each_tenant_chunked_by_batch_size(self) -> None:
        t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
        rows = self._rows({t1: 5, t2: 2})
        sizes_by_tenant: dict[str, list[int]] = {}
        for batch in cmd.iter_tenant_batches(rows, batch_size=2):
            sizes_by_tenant.setdefault(batch[0].das_tenant_id, []).append(len(batch))
        assert sorted(sizes_by_tenant[t1]) == [1, 2, 2]
        assert sorted(sizes_by_tenant[t2]) == [2]


class TestSnapshotName:
    def test_default_snapshot_name_format(self) -> None:
        name = cmd.default_snapshot_name(datetime(2026, 6, 30, 14, 15, 0, tzinfo=timezone.utc))
        assert name == "activity_eventtype_bak_20260630_141500"

    def test_default_snapshot_name_is_a_safe_identifier(self) -> None:
        name = cmd.default_snapshot_name()
        assert cmd._SNAPSHOT_NAME_RE.match(name)


def _insert_event_type(
    *,
    et_id: str,
    das_tenant_id: str,
    schema: str,
    value: str,
    version: str = "2",
    updated_at: datetime | None = None,
) -> None:
    """Insert one activity_eventtype row via raw SQL.

    Raw SQL sidesteps the tenant-scoped ORM manager (and the EventCategory
    SubFactory's get_or_create, which trips tenant scoping in this off-Citus
    test DB). category_id is nullable, so it is omitted.
    """
    stamp = updated_at or datetime.now(tz=timezone.utc)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO activity_eventtype
                (id, created_at, updated_at, value, display, ordernum, schema,
                 is_collection, default_priority, default_state, auto_resolve,
                 is_active, geometry_type, das_tenant_id, version, readonly)
            VALUES (%s, now(), %s, %s, %s, 1, %s, false, 0, 'new', false,
                    true, 'Point', %s, %s, false)
            """,
            [et_id, stamp, value, value, schema, das_tenant_id, version],
        )


@pytest.mark.django_db
class TestDbWritePath:
    """Composite-key write path with two real tenants.

    Off-Citus, activity_eventtype.id is a true unique PK, so we cannot store two
    physical rows sharing an id. We therefore give each tenant's live row a
    DISTINCT id, and make each id ``shared`` in the BACKUP CSV by pairing it with
    a decoy (id, decoy-tenant) entry that has no live row. Shared-id detection
    (purely CSV-derived) then selects both live rows as targets, exercising the
    composite (id, das_tenant_id) update across two tenants.
    """

    def _two_tenants(self) -> tuple[str, str]:
        tenant_a = TenantFactory(id=uuid.uuid4(), domain=f"a-{uuid.uuid4().hex[:8]}.example.com")
        tenant_b = TenantFactory(id=uuid.uuid4(), domain=f"b-{uuid.uuid4().hex[:8]}.example.com")
        return str(tenant_a.id), str(tenant_b.id)

    def _decoy_tenant(self) -> str:
        """A real third tenant with one (non-target) live row.

        It backs the CSV decoy entries that make an id ``shared`` across tenants.
        Off-Citus we can't reuse a PK, so the decoy tenant must own its own
        physical row for the wrong-backup overlap check to count it as present.
        """
        tenant = TenantFactory(id=uuid.uuid4(), domain=f"decoy-{uuid.uuid4().hex[:8]}.example.com")
        _insert_event_type(
            et_id=str(uuid.uuid4()), das_tenant_id=str(tenant.id), schema='{"decoy": true}', value="decoy"
        )
        return str(tenant.id)

    def _raw_schema(self, et_id: str) -> str:
        with connection.cursor() as cur:
            cur.execute("SELECT schema FROM activity_eventtype WHERE id = %s", [et_id])
            return cur.fetchone()[0]

    def _raw_updated_at(self, et_id: str) -> datetime:
        with connection.cursor() as cur:
            cur.execute("SELECT updated_at FROM activity_eventtype WHERE id = %s", [et_id])
            return cur.fetchone()[0]

    def _snapshot_schema(self, snapshot: str, et_id: str) -> str:
        with connection.cursor() as cur:
            cur.execute(f'SELECT schema FROM "{snapshot}" WHERE id = %s', [et_id])
            return cur.fetchone()[0]

    def _unique_snapshot_name(self) -> str:
        return f"activity_eventtype_bak_test_{uuid.uuid4().hex}"

    def test_commit_restores_each_row_to_its_own_backup(self, tmp_path, capsys) -> None:
        tenant_a, tenant_b = self._two_tenants()
        id_a, id_b, id_untouched = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        decoy = self._decoy_tenant()
        _insert_event_type(et_id=id_a, das_tenant_id=tenant_a, schema='{"clobbered": "A"}', value="et_a")
        _insert_event_type(et_id=id_b, das_tenant_id=tenant_b, schema='{"clobbered": "B"}', value="et_b")
        # A non-target row: its id is NOT shared in the backup, so it is excluded.
        _insert_event_type(
            et_id=id_untouched, das_tenant_id=tenant_a, schema='{"clobbered": "U"}', value="et_untouched"
        )

        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_a, das_tenant_id=tenant_a, schema='{"restored": "A"}', value="et_a"),
                _csv_record(id=id_a, das_tenant_id=decoy, schema='{"restored": "A"}', value="et_a"),
                _csv_record(id=id_b, das_tenant_id=tenant_b, schema='{"restored": "B"}', value="et_b"),
                _csv_record(id=id_b, das_tenant_id=decoy, schema='{"restored": "B"}', value="et_b"),
                # Non-shared id → never a target.
                _csv_record(id=id_untouched, das_tenant_id=tenant_a, schema='{"restored": "U"}', value="et_untouched"),
            ],
        )
        snapshot = self._unique_snapshot_name()
        call_command("restore_clobbered_event_type_schemas", str(path), "--commit", "--snapshot-table", snapshot)
        out = capsys.readouterr().out

        assert self._raw_schema(id_a) == '{"restored": "A"}'
        assert self._raw_schema(id_b) == '{"restored": "B"}'
        # Non-target row keeps its live (clobbered) schema — never matched.
        assert self._raw_schema(id_untouched) == '{"clobbered": "U"}'

        # Snapshot exists and holds the PRE-restore schemas.
        assert cmd.snapshot_table_exists(snapshot)
        assert f"Snapshot created: {snapshot}" in out
        assert self._snapshot_schema(snapshot, id_a) == '{"clobbered": "A"}'
        assert self._snapshot_schema(snapshot, id_b) == '{"clobbered": "B"}'

        # Sample reflects only the rows that actually changed (et_a, et_b), not
        # the non-target row.
        assert "Sample of rows changed" in out
        assert "et_a" in out and "et_b" in out
        assert "et_untouched" not in out
        assert "Restored 2 row(s)." in out

    def test_existing_snapshot_table_aborts(self, tmp_path) -> None:
        tenant_a, _ = self._two_tenants()
        id_a, decoy = str(uuid.uuid4()), self._decoy_tenant()
        _insert_event_type(et_id=id_a, das_tenant_id=tenant_a, schema='{"clobbered": "A"}', value="et_a")
        snapshot = self._unique_snapshot_name()
        with connection.cursor() as cur:
            cur.execute(f'CREATE TABLE "{snapshot}" (x int)')
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_a, das_tenant_id=tenant_a, schema='{"restored": "A"}', value="et_a"),
                _csv_record(id=id_a, das_tenant_id=decoy, schema='{"restored": "A"}', value="et_a"),
            ],
        )
        with pytest.raises(CommandError, match="already exists"):
            call_command("restore_clobbered_event_type_schemas", str(path), "--commit", "--snapshot-table", snapshot)
        # The restore must not have run.
        assert self._raw_schema(id_a) == '{"clobbered": "A"}'

    def test_updated_at_advances_to_now(self, tmp_path) -> None:
        tenant_a, _ = self._two_tenants()
        id_a, decoy = str(uuid.uuid4()), self._decoy_tenant()
        _insert_event_type(
            et_id=id_a,
            das_tenant_id=tenant_a,
            schema='{"clobbered": "A"}',
            value="et_a",
            updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_a, das_tenant_id=tenant_a, schema='{"restored": "A"}', value="et_a"),
                _csv_record(id=id_a, das_tenant_id=decoy, schema='{"restored": "A"}', value="et_a"),
            ],
        )
        call_command(
            "restore_clobbered_event_type_schemas",
            str(path),
            "--commit",
            "--snapshot-table",
            self._unique_snapshot_name(),
        )
        assert self._raw_updated_at(id_a) > datetime(2020, 1, 1, tzinfo=timezone.utc)

    def test_row_already_equal_to_backup_is_a_noop(self, tmp_path, capsys) -> None:
        tenant_a, _ = self._two_tenants()
        id_a, decoy = str(uuid.uuid4()), self._decoy_tenant()
        already = '{"restored": "A"}'
        _insert_event_type(et_id=id_a, das_tenant_id=tenant_a, schema=already, value="et_a")
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_a, das_tenant_id=tenant_a, schema=already, value="et_a"),
                _csv_record(id=id_a, das_tenant_id=decoy, schema=already, value="et_a"),
            ],
        )
        call_command(
            "restore_clobbered_event_type_schemas",
            str(path),
            "--commit",
            "--snapshot-table",
            self._unique_snapshot_name(),
        )
        out = capsys.readouterr().out
        # IS DISTINCT FROM guard means the already-equal row is excluded from the
        # changed set, so nothing is reported as changed.
        assert "Restored 0 row(s)." in out

    def test_dry_run_writes_nothing(self, tmp_path, capsys) -> None:
        tenant_a, _ = self._two_tenants()
        id_a, decoy = str(uuid.uuid4()), self._decoy_tenant()
        _insert_event_type(et_id=id_a, das_tenant_id=tenant_a, schema='{"clobbered": "A"}', value="et_a")
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_a, das_tenant_id=tenant_a, schema='{"restored": "A"}', value="et_a"),
                _csv_record(id=id_a, das_tenant_id=decoy, schema='{"restored": "A"}', value="et_a"),
            ],
        )
        call_command("restore_clobbered_event_type_schemas", str(path))
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "WOULD change" in out
        assert "Sample of rows would change" in out
        assert "et_a" in out
        # Live schema unchanged and no snapshot created on dry-run.
        assert self._raw_schema(id_a) == '{"clobbered": "A"}'
        assert "Snapshot created" not in out

    def test_wrong_backup_aborts_when_tenants_absent(self, tmp_path) -> None:
        # All target tenant ids are random and absent from the DB.
        shared_id = str(uuid.uuid4())
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=shared_id, das_tenant_id=str(uuid.uuid4()), schema='{"x": 1}', value="a"),
                _csv_record(id=shared_id, das_tenant_id=str(uuid.uuid4()), schema='{"x": 2}', value="a"),
            ],
        )
        with pytest.raises(CommandError, match="wrong"):
            call_command("restore_clobbered_event_type_schemas", str(path), "--commit")

    def test_missing_csv_aborts(self, tmp_path) -> None:
        with pytest.raises(CommandError, match="not found"):
            call_command("restore_clobbered_event_type_schemas", str(tmp_path / "nope.csv"))

    def test_naive_modified_between_aborts(self, tmp_path) -> None:
        tenant_a, _ = self._two_tenants()
        id_a, decoy = str(uuid.uuid4()), self._decoy_tenant()
        _insert_event_type(et_id=id_a, das_tenant_id=tenant_a, schema='{"clobbered": "A"}', value="et_a")
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_a, das_tenant_id=tenant_a, schema='{"restored": "A"}', value="et_a"),
                _csv_record(id=id_a, das_tenant_id=decoy, schema='{"restored": "A"}', value="et_a"),
            ],
        )
        with pytest.raises(CommandError, match="timezone-naive"):
            call_command(
                "restore_clobbered_event_type_schemas",
                str(path),
                "--modified-between",
                "2026-06-29 00:00:00",
                "2026-06-30 00:00:00+00:00",
            )

    def _setup_window_scenario(self, tmp_path) -> tuple[str, str, str]:
        """Two differing target rows in one tenant: one updated inside the
        migration window, one updated after it. Returns (csv_path, id_in, id_out).
        """
        tenant_a, _ = self._two_tenants()
        decoy = self._decoy_tenant()
        id_in, id_out = str(uuid.uuid4()), str(uuid.uuid4())
        # Inside [2026-06-29, 2026-06-30): clobbered by the migration.
        _insert_event_type(
            et_id=id_in,
            das_tenant_id=tenant_a,
            schema='{"clobbered": "IN"}',
            value="et_in",
            updated_at=datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc),
        )
        # Outside the window: a legitimate post-migration edit we must NOT revert.
        _insert_event_type(
            et_id=id_out,
            das_tenant_id=tenant_a,
            schema='{"clobbered": "OUT"}',
            value="et_out",
            updated_at=datetime(2026, 6, 30, 9, 0, tzinfo=timezone.utc),
        )
        path = tmp_path / "backup.csv"
        _write_csv(
            path,
            [
                _csv_record(id=id_in, das_tenant_id=tenant_a, schema='{"restored": "IN"}', value="et_in"),
                _csv_record(id=id_in, das_tenant_id=decoy, schema='{"restored": "IN"}', value="et_in"),
                _csv_record(id=id_out, das_tenant_id=tenant_a, schema='{"restored": "OUT"}', value="et_out"),
                _csv_record(id=id_out, das_tenant_id=decoy, schema='{"restored": "OUT"}', value="et_out"),
            ],
        )
        return str(path), id_in, id_out

    def test_modified_between_restores_only_in_window_row(self, tmp_path) -> None:
        path, id_in, id_out = self._setup_window_scenario(tmp_path)
        call_command(
            "restore_clobbered_event_type_schemas",
            path,
            "--commit",
            "--snapshot-table",
            self._unique_snapshot_name(),
            "--modified-between",
            "2026-06-29 00:00:00+00:00",
            "2026-06-30 00:00:00+00:00",
        )
        # In-window row restored; out-of-window (post-migration edit) untouched.
        assert self._raw_schema(id_in) == '{"restored": "IN"}'
        assert self._raw_schema(id_out) == '{"clobbered": "OUT"}'

    def test_without_window_both_rows_are_restored(self, tmp_path) -> None:
        path, id_in, id_out = self._setup_window_scenario(tmp_path)
        call_command(
            "restore_clobbered_event_type_schemas",
            path,
            "--commit",
            "--snapshot-table",
            self._unique_snapshot_name(),
        )
        assert self._raw_schema(id_in) == '{"restored": "IN"}'
        assert self._raw_schema(id_out) == '{"restored": "OUT"}'
