"""Tests for the ``rebuild_event_tsvectors`` management command (ERA-13500).

The command is deliberately cross-tenant, so the load-bearing behaviour is that
``--tenant_domain`` rebuilds *only* the named site's rows. That is verified
against two real tenants, with all setup and verification done in raw SQL to
sidestep the tenant-scoped ORM managers (the same approach
``test_restore_clobbered_event_type_schemas`` takes).

The SQL builders are also unit-tested without a database, to pin the invariant
that no statement can ever be emitted without a ``das_tenant_id`` predicate.
"""

from __future__ import annotations

import json
import uuid

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from activity import tsvector_rebuild
from factories import TenantFactory

# A choice option that lives in the event type schema but not on the event.
SCHEMA_ONLY_TERM = "mokgadi"
# The option actually selected on the event.
SELECTED_TERM = "thandi"


def _event_type_schema() -> str:
    return json.dumps(
        {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "properties": {
                    "rhino_name": {
                        "type": "string",
                        "title": "Rhino Name",
                        "enum": [SCHEMA_ONLY_TERM, SELECTED_TERM],
                        "enumNames": {SCHEMA_ONLY_TERM: "Mokgadi", SELECTED_TERM: "Thandi"},
                    },
                },
            },
            "definition": ["rhino_name"],
        }
    )


def _insert_event_type(*, das_tenant_id: str) -> str:
    """Insert one activity_eventtype row via raw SQL, returning its id.

    Off-Citus each tenant needs its own id (the physical PK is just ``id``), so
    callers get a distinct event type per tenant. category_id is nullable and is
    omitted.
    """
    event_type_id = str(uuid.uuid4())
    value = f"rhino_sighting_{uuid.uuid4().hex[:8]}"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO activity_eventtype
                (id, created_at, updated_at, value, display, ordernum, schema,
                 is_collection, default_priority, default_state, auto_resolve,
                 is_active, geometry_type, das_tenant_id, version, readonly)
            VALUES (%s, now(), now(), %s, 'Rhinowatch Sighting', 1, %s, false, 0, 'new', false,
                    true, 'Point', %s, '1', false)
            """,
            [event_type_id, value, _event_type_schema(), das_tenant_id],
        )
    return event_type_id


def _insert_event(*, das_tenant_id: str, event_type_id: str, title: str) -> str:
    """Insert an event plus its details row, returning the event id.

    Inserting the details row fires ``tsvector_doc_trigger``, which is what
    creates the ``activity_tsvectormodel`` row -- the same path a real event
    takes.
    """
    event_id = str(uuid.uuid4())
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO activity_event
                (created_at, updated_at, id, provenance, attributes, message, event_time,
                 priority, state, sort_at, das_tenant_id, event_type_id, title)
            VALUES (now(), now(), %s, 'system', '{}'::jsonb, '', now(), 0, 'new', now(), %s, %s, %s)
            """,
            [event_id, das_tenant_id, event_type_id, title],
        )
        cursor.execute(
            """
            INSERT INTO activity_eventdetails (created_at, updated_at, id, data, event_id, das_tenant_id)
            VALUES (now(), now(), %s, %s::jsonb, %s, %s)
            """,
            [
                str(uuid.uuid4()),
                json.dumps({"event_details": {"rhino_name": SELECTED_TERM}}),
                event_id,
                das_tenant_id,
            ],
        )
    return event_id


def _poison_with_schema_term(event_id: str) -> None:
    """Recreate a pre-0205 row: schema text welded into the vector at weight B."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE activity_tsvectormodel ts
            SET tsvector_event = coalesce(ts.tsvector_event, ''::tsvector) ||
                                 setweight(to_tsvector(et.schema::text), 'B')
            FROM activity_event e
                     JOIN activity_eventtype et ON et.id = e.event_type_id
                                               AND et.das_tenant_id = e.das_tenant_id
            WHERE ts.event_id = e.id
              AND ts.das_tenant_id = e.das_tenant_id
              AND e.id = %s
            """,
            [event_id],
        )


def _has_schema_term(event_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tsvector_event @@ to_tsquery(%s) FROM activity_tsvectormodel WHERE event_id = %s",
            [f"{SCHEMA_ONLY_TERM}:*", event_id],
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def _has_term(event_id: str, term: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tsvector_event @@ to_tsquery(%s) FROM activity_tsvectormodel WHERE event_id = %s",
            [f"{term}:*", event_id],
        )
        row = cursor.fetchone()
    return bool(row and row[0])


class TestSqlConstruction:
    """No database: pin the tenant predicates into the generated SQL."""

    def test_rebuild_sql_always_scopes_the_write_by_tenant(self) -> None:
        sql, _ = tsvector_rebuild.build_rebuild_batch_query(
            upper_bound=(uuid.uuid4(), uuid.uuid4()), cursor_key=None, das_tenant_id=None
        )

        assert "ts.das_tenant_id = e.das_tenant_id" in sql

    def test_rebuild_sql_pins_a_single_tenant_when_given_one(self) -> None:
        tenant_id = uuid.uuid4()

        sql, params = tsvector_rebuild.build_rebuild_batch_query(
            upper_bound=(uuid.uuid4(), uuid.uuid4()), cursor_key=None, das_tenant_id=tenant_id
        )

        assert "ts.das_tenant_id = %s::uuid" in sql
        assert str(tenant_id) in params

    def test_rebuild_sql_joins_event_type_on_tenant_as_well_as_id(self) -> None:
        sql, _ = tsvector_rebuild.build_rebuild_batch_query(
            upper_bound=(uuid.uuid4(), uuid.uuid4()), cursor_key=None, das_tenant_id=None
        )

        assert "et.das_tenant_id = e.das_tenant_id" in sql

    def test_rebuild_sql_never_mentions_the_event_type_schema(self) -> None:
        sql, _ = tsvector_rebuild.build_rebuild_batch_query(
            upper_bound=(uuid.uuid4(), uuid.uuid4()), cursor_key=None, das_tenant_id=None
        )

        assert "et.schema" not in sql

    def test_param_count_matches_placeholders_in_every_mode(self) -> None:
        upper_bound = (uuid.uuid4(), uuid.uuid4())
        cursor_key = (uuid.uuid4(), uuid.uuid4())
        for das_tenant_id in (None, uuid.uuid4()):
            for key in (None, cursor_key):
                for sql, params in (
                    tsvector_rebuild.build_upper_bound_query(
                        cursor_key=key, das_tenant_id=das_tenant_id, batch_size=10
                    ),
                    tsvector_rebuild.build_rebuild_batch_query(
                        upper_bound=upper_bound, cursor_key=key, das_tenant_id=das_tenant_id
                    ),
                ):
                    assert sql.count("%s") == len(params)

    def test_upper_bound_query_is_unfiltered_on_the_first_all_tenants_pass(self) -> None:
        sql, params = tsvector_rebuild.build_upper_bound_query(cursor_key=None, das_tenant_id=None, batch_size=10)

        assert "WHERE" not in sql
        assert params == [10]


@pytest.mark.django_db
class TestRebuildEventTsvectorsCommand:
    def _site(self) -> tuple[str, str]:
        """A DASTenant plus one event of its own type, poisoned. Returns (domain, event_id)."""
        tenant = TenantFactory(id=uuid.uuid4(), domain=f"site-{uuid.uuid4().hex[:8]}.example.com")
        tenant_id = str(tenant.id)
        event_type_id = _insert_event_type(das_tenant_id=tenant_id)
        event_id = _insert_event(das_tenant_id=tenant_id, event_type_id=event_type_id, title="Sighting near the dam")
        _poison_with_schema_term(event_id)
        return tenant.domain, event_id

    def test_single_site_mode_rebuilds_only_the_named_site(self) -> None:
        domain_a, event_a = self._site()
        _, event_b = self._site()
        assert _has_schema_term(event_a)
        assert _has_schema_term(event_b)

        call_command("rebuild_event_tsvectors", "--tenant_domain", domain_a)

        assert not _has_schema_term(event_a)
        assert _has_schema_term(event_b), "another site's rows must not be touched"

    def test_single_site_mode_keeps_real_event_content_searchable(self) -> None:
        domain, event_id = self._site()

        call_command("rebuild_event_tsvectors", "--tenant_domain", domain)

        assert _has_term(event_id, SELECTED_TERM)
        assert _has_term(event_id, "dam")
        assert _has_term(event_id, "rhinowatch")

    def test_all_tenants_mode_rebuilds_every_site(self) -> None:
        _, event_a = self._site()
        _, event_b = self._site()

        call_command("rebuild_event_tsvectors", "--all-tenants")

        assert not _has_schema_term(event_a)
        assert not _has_schema_term(event_b)

    def test_small_batch_size_still_walks_every_row(self) -> None:
        _, event_a = self._site()
        _, event_b = self._site()

        call_command("rebuild_event_tsvectors", "--all-tenants", "--batch-size", "1")

        assert not _has_schema_term(event_a)
        assert not _has_schema_term(event_b)

    def test_rebuilding_twice_is_a_noop(self) -> None:
        domain, event_id = self._site()

        call_command("rebuild_event_tsvectors", "--tenant_domain", domain)
        call_command("rebuild_event_tsvectors", "--tenant_domain", domain)

        assert not _has_schema_term(event_id)
        assert _has_term(event_id, SELECTED_TERM)

    def test_reports_the_number_of_rows_rebuilt(self, capsys: pytest.CaptureFixture[str]) -> None:
        domain, _ = self._site()

        call_command("rebuild_event_tsvectors", "--tenant_domain", domain)

        out = capsys.readouterr().out
        assert domain in out
        assert "Rebuilt 1 event tsvector row(s)" in out

    def test_unknown_site_aborts(self) -> None:
        with pytest.raises(CommandError, match="No site found with domain"):
            call_command("rebuild_event_tsvectors", "--tenant_domain", "nope.example.com")

    def test_no_mode_aborts(self) -> None:
        with pytest.raises(CommandError, match="--tenant_domain"):
            call_command("rebuild_event_tsvectors")

    def test_both_modes_aborts(self) -> None:
        domain, _ = self._site()

        with pytest.raises(CommandError, match="not both"):
            call_command("rebuild_event_tsvectors", "--tenant_domain", domain, "--all-tenants")

    def test_zero_batch_size_aborts(self) -> None:
        with pytest.raises(CommandError, match="--batch-size must be >= 1"):
            call_command("rebuild_event_tsvectors", "--all-tenants", "--batch-size", "0")
