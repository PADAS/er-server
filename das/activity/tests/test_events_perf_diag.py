"""Diagnostic: print all queries executed by the events list view."""

import re
from collections import Counter

import pytest

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from activity.models import EventRelationship
from activity.views import EventsView
from client_http import HTTPClient
from factories import EventFactory, EventNoteFactory, EventTypeFactory

N_EVENTS = 25
N_WITH_NOTES = 5
N_WITH_RELATIONS = 5


@pytest.fixture
def perf_dataset(five_event_categories):
    cat = five_event_categories[0]
    event_types = EventTypeFactory.create_batch(3, category=cat)
    events = [EventFactory.create(event_type=event_types[i % len(event_types)]) for i in range(N_EVENTS)]
    for event in events[:N_WITH_NOTES]:
        EventNoteFactory.create_batch(2, event=event)
    collection = events[0]
    collection.event_type.is_collection = True
    collection.event_type.save()
    for child in events[1 : N_WITH_RELATIONS + 1]:
        EventRelationship.objects.add_relationship(from_event=collection, to_event=child, type="contains")
    return events


def _table(sql: str) -> str:
    """Best-effort extraction of the primary table from a SQL statement."""
    m = re.search(r'FROM\s+"?(\w+)"?', sql, re.IGNORECASE)
    return m.group(1) if m else sql[:60]


@pytest.mark.perf
@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch", "perf_dataset")
class TestEventsQueryDiag:
    def _make_client(self):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        return client

    def _run(self, params=None, client=None):
        if client is None:
            client = self._make_client()
        request = client.factory.get(reverse("events"), params or {})
        client.force_authenticate(request, client.app_user)
        with CaptureQueriesContext(connection) as ctx:
            response = EventsView.as_view()(request)
        assert response.status_code == 200
        return ctx.captured_queries, response

    def test_full_set_of_queries(self):
        client = self._make_client()
        queries, response = self._run(client=client)
        tally = Counter()
        for i, q in enumerate(queries, 1):
            table = _table(q["sql"])
            tally[table] += 1
            print(f"  {i:3}. [{table}] {q['sql'][:120]}")
        print(f"\nTotal: {len(queries)} queries")
        print("\nBy table:")
        for table, count in tally.most_common():
            print(f"  {count:3}x  {table}")

        data = response.data
        assert data["count"] == N_EVENTS, f"Expected {N_EVENTS} total events, got {data['count']}"
        results = data["results"]
        assert len(results) == N_EVENTS, f"Expected {N_EVENTS} results on first page, got {len(results)}"

        ids = [r["id"] for r in results]
        assert len(ids) == len(set(ids)), "Duplicate event IDs returned in response"

        for r in results:
            assert "id" in r
            assert "message" in r
            assert "event_type" in r
            assert "is_collection" in r

        # Verify relationships are serialized when explicitly requested
        _, response_with_relations = self._run({"include_related_events": "true"}, client=client)
        results_with_relations = response_with_relations.data["results"]
        events_with_children = [r for r in results_with_relations if r.get("contains")]
        assert (
            len(events_with_children) == 1
        ), f"Expected exactly 1 event with children, got {len(events_with_children)}"
        assert len(events_with_children[0]["contains"]) == N_WITH_RELATIONS, (
            f"Collection event should contain {N_WITH_RELATIONS} children, "
            f"got {len(events_with_children[0]['contains'])}"
        )

        # Verify notes are included and correct when explicitly requested
        queries_with_notes, response_with_notes = self._run({"include_notes": "true"}, client=client)
        results_with_notes = response_with_notes.data["results"]
        events_having_notes = [r for r in results_with_notes if r.get("notes")]
        assert (
            len(events_having_notes) == N_WITH_NOTES
        ), f"Expected {N_WITH_NOTES} events with notes, got {len(events_having_notes)}"
        for event in events_having_notes:
            assert (
                len(event["notes"]) == 2
            ), f"Expected 2 notes per event, got {len(event['notes'])} for event {event['id']}"
