"""
Tests for EventFilteringQuerySet.by_exclude_contained.

These lock in the ERA performance fix that replaced Django's split_exclude
anti-join (which compiled to a subquery on activity_eventrelationship with no
leading das_tenant_id literal — only a cross-table tenant-equality join
condition — causing a full-index scan on evtrel_tenant_to_evt_idx for every
candidate row) with a tenant-scoped Exists() subquery.

Production EXPLAIN ANALYZE: 25,239 candidate rows × 132 buffer probes each
= 3.33M buffer hits, 9.4s of a 10.2s query. The anti-join subquery lacked
the leading das_tenant_id literal, so Postgres scanned the full index per
probe instead of probing by (tenant, to_event).

The tests assert two things:

1. SQL shape: the generated EXISTS subquery on activity_eventrelationship
   carries a das_tenant_id = <literal> predicate (not just the cross-table
   tenant-equality condition from TenantForeignKey), ensuring Postgres can
   probe evtrel_tenant_to_evt_idx by (tenant, to_event).
2. Behavioural correctness: events that are the to_event of a "contains"
   relationship are excluded; events with no relationships or with a
   non-"contains" relationship are not excluded; passing False is a no-op.

Note on cross-tenant behavioral coverage: a behavioral regression test for
tenant scoping is structurally impossible here. Event PKs are globally-unique
UUIDs, so an EventRelationship row belonging to another tenant can never have
a to_event_id that collides with a current-tenant event's id. The SQL-shape
test (test_exists_subquery_contains_tenant_literal_not_just_cross_table_join)
is the correct and sufficient regression guard for the tenant-scoping fix.
"""

from __future__ import annotations

import pytest

from activity.models import Event, EventRelationship, EventRelationshipType


def _create_event(das_tenant, title: str) -> Event:
    return Event.objects.create(title=title, das_tenant=das_tenant)


def _get_or_create_relationship_type(value: str, das_tenant, *, symmetrical: bool = False) -> EventRelationshipType:
    obj, _ = EventRelationshipType.objects.get_or_create(
        das_tenant=das_tenant,
        value=value,
        defaults={"ordernum": 1, "symmetrical": symmetrical},
    )
    return obj


def _create_relationship(
    from_event: Event,
    to_event: Event,
    rel_type: EventRelationshipType,
    das_tenant,
) -> EventRelationship:
    return EventRelationship.objects.create(
        from_event=from_event,
        to_event=to_event,
        type=rel_type,
        das_tenant=das_tenant,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestByExcludeContainedSQLShape:
    """The compiled EXISTS subquery must carry a das_tenant_id = <literal>
    predicate so the index probe uses the leading tenant column of
    evtrel_tenant_to_evt_idx.

    The old split_exclude form only emitted a cross-table join condition
    (U1.das_tenant_id = U2.das_tenant_id) — which contains the column name
    but provides no selectivity against the leading index column at query time.
    The fix uses Exists() through the TenantManagerMixin which injects the
    literal tenant id into the subquery WHERE clause.
    """

    def test_exists_subquery_contains_tenant_literal_not_just_cross_table_join(self, das_tenant):
        """by_exclude_contained(True) must emit an EXISTS subquery where the
        activity_eventrelationship table is filtered by a das_tenant_id literal,
        not only by the cross-table join condition
        (U1.das_tenant_id = U2.das_tenant_id) that the old split_exclude
        produced.

        Old SQL (bug): EXISTS(... WHERE U1.das_tenant_id = U2.das_tenant_id ...)
          — tenant id only in the outer WHERE, not in the subquery.
        New SQL (fix): EXISTS(... WHERE U1.das_tenant_id = <literal> ...)
          — tenant id literal appears inside the subquery so Postgres can use
            the leading column of evtrel_tenant_to_evt_idx.
        """
        qs = Event.objects.all().by_exclude_contained(True)
        sql = str(qs.query)

        # The EXISTS subquery must reference activity_eventrelationship
        assert (
            "activity_eventrelationship" in sql.lower()
        ), f"by_exclude_contained must reference activity_eventrelationship; SQL: {sql}"
        assert "EXISTS" in sql, f"by_exclude_contained must use an EXISTS subquery; SQL: {sql}"

        # Extract the content of the EXISTS(…) subquery only — we want the
        # tenant literal to appear INSIDE the subquery, not just in the outer
        # WHERE clause (which is where the old split_exclude put it via the
        # EventManager's automatic tenant filter on the outer Event query).
        exists_start = sql.index("EXISTS")
        # Walk forward past the opening paren to find the matching close paren.
        depth = 0
        subquery_end = exists_start
        for i, ch in enumerate(sql[exists_start:], start=exists_start):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    subquery_end = i + 1
                    break
        exists_subquery = sql[exists_start:subquery_end]

        tenant_id_literal = str(das_tenant.id)
        assert tenant_id_literal in exists_subquery, (
            f"The EXISTS subquery on activity_eventrelationship must contain the "
            f"das_tenant_id literal ({tenant_id_literal}) as a WHERE predicate. "
            f"Old split_exclude only put it in the outer query; the fix must also "
            f"put it inside the subquery.\nSubquery: {exists_subquery}"
        )

    def test_false_value_returns_unmodified_queryset_with_no_subquery(self):
        """by_exclude_contained(False) is a no-op and must not add any
        subquery against activity_eventrelationship."""
        qs = Event.objects.all().by_exclude_contained(False)
        sql = str(qs.query).lower()

        assert "activity_eventrelationship" not in sql, (
            "by_exclude_contained(False) must not reference activity_eventrelationship; " f"SQL: {sql}"
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestByExcludeContainedBehavior:
    """Functional correctness: which events are included/excluded."""

    def test_contained_event_is_excluded(self, das_tenant):
        """An event that is the to_event of a 'contains' relationship must be
        excluded when exclude_contained=True."""
        contains_type = _get_or_create_relationship_type("contains", das_tenant)
        collection = _create_event(das_tenant, "Collection")
        contained = _create_event(das_tenant, "Contained")
        _create_relationship(collection, contained, contains_type, das_tenant)

        result_ids = set(Event.objects.all().by_exclude_contained(True).values_list("id", flat=True))

        assert contained.id not in result_ids, "Contained event must be excluded"
        assert collection.id in result_ids, "Collection (from_event) must not be excluded"

    def test_event_with_no_relationship_is_not_excluded(self, das_tenant):
        """An event with no EventRelationship records must survive the filter."""
        standalone = _create_event(das_tenant, "Standalone")

        result_ids = set(Event.objects.all().by_exclude_contained(True).values_list("id", flat=True))

        assert standalone.id in result_ids, "Event with no relationships must not be excluded"

    def test_event_with_non_contains_relationship_type_is_not_excluded(self, das_tenant):
        """An event that is the to_event of a non-'contains' relationship
        (e.g. 'is_linked_to') must NOT be excluded."""
        linked_type = _get_or_create_relationship_type("is_linked_to", das_tenant, symmetrical=True)
        event_a = _create_event(das_tenant, "Event A")
        event_b = _create_event(das_tenant, "Event B")
        _create_relationship(event_a, event_b, linked_type, das_tenant)

        result_ids = set(Event.objects.all().by_exclude_contained(True).values_list("id", flat=True))

        assert event_b.id in result_ids, "Event linked via a non-'contains' relationship must not be excluded"

    def test_false_value_returns_all_events_including_contained(self, das_tenant):
        """by_exclude_contained(False) must be a no-op: contained events are
        still present in the result set."""
        contains_type = _get_or_create_relationship_type("contains", das_tenant)
        collection = _create_event(das_tenant, "Coll")
        contained = _create_event(das_tenant, "Cont")
        _create_relationship(collection, contained, contains_type, das_tenant)

        result_ids = set(Event.objects.all().by_exclude_contained(False).values_list("id", flat=True))

        assert contained.id in result_ids, "by_exclude_contained(False) must not filter out contained events"
