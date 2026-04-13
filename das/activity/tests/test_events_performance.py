"""
Performance tests for the /api/v1.0/activity/events endpoint.

Measures query count and wall-clock time for the events list view across
realistic scenarios: plain list, with notes, with files, with relationships.
Run before/after optimizations to quantify improvements.
"""

import time

import pytest

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from activity.models import EventRelationship
from activity.views import EventsView
from client_http import HTTPClient
from factories import EventFactory, EventNoteFactory, EventTypeFactory

N_EVENTS = 25
N_WITH_NOTES = 5  # events that get 2 notes each
N_WITH_RELATIONS = 5  # events that are children of a collection event


@pytest.fixture
def perf_dataset(five_event_categories):
    """
    Creates N_EVENTS events with a realistic mix of notes and relationships.
    All objects land in the shared test tenant via TenantFactory's fixed UUID.
    """
    cat = five_event_categories[0]
    event_types = EventTypeFactory.create_batch(3, category=cat)

    events = [EventFactory.create(event_type=event_types[i % len(event_types)]) for i in range(N_EVENTS)]

    # Add 2 notes to the first N_WITH_NOTES events
    for event in events[:N_WITH_NOTES]:
        EventNoteFactory.create_batch(2, event=event)

    # Make the first event a collection containing the next N_WITH_RELATIONS
    collection = events[0]
    collection.event_type.is_collection = True
    collection.event_type.save()
    for child in events[1 : N_WITH_RELATIONS + 1]:
        EventRelationship.objects.add_relationship(from_event=collection, to_event=child, type="contains")

    return events


def _run_list(url: str, params: dict = None) -> tuple[int, float, int]:
    """Returns (status_code, elapsed_seconds, query_count)."""
    client = HTTPClient()
    client.app_user.is_superuser = True
    client.app_user.save()
    request = client.factory.get(url, params or {})
    client.force_authenticate(request, client.app_user)

    with CaptureQueriesContext(connection) as ctx:
        t0 = time.perf_counter()
        response = EventsView.as_view()(request)
        elapsed = time.perf_counter() - t0

    return response.status_code, elapsed, len(ctx.captured_queries)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch", "perf_dataset")
class TestEventsPerformance:
    def test_plain_list_query_count(self):
        """Base list — no optional includes.
        Baseline (before optimizations): 87 queries for 25 events.
        """
        status, elapsed, queries = _run_list(reverse("events"))
        print(f"\n[plain list] {N_EVENTS} events, queries={queries}, time={elapsed:.3f}s")
        assert status == 200
        assert queries <= 70, f"Expected ≤70 queries for plain list, got {queries}"

    def test_include_notes_query_count(self):
        """With include_notes=true — added select_related(created_by_user) to notes prefetch.
        Baseline (before optimizations): 98 queries for 25 events (5 with notes).
        """
        status, elapsed, queries = _run_list(reverse("events"), {"include_notes": "true"})
        print(
            f"\n[include_notes] {N_EVENTS} events ({N_WITH_NOTES} with notes),"
            f" queries={queries}, time={elapsed:.3f}s"
        )
        assert status == 200
        assert queries <= 80, f"Expected ≤80 queries with include_notes, got {queries}"

    def test_include_files_query_count(self):
        """With include_files=true — added select_related(created_by) to files prefetch.
        Baseline (before optimizations): 87 queries for 25 events.
        """
        status, elapsed, queries = _run_list(reverse("events"), {"include_files": "true"})
        print(f"\n[include_files] {N_EVENTS} events, queries={queries}, time={elapsed:.3f}s")
        assert status == 200
        assert queries <= 70, f"Expected ≤70 queries with include_files, got {queries}"

    def test_relationships_no_n_plus_1(self):
        """Relationship select_related(type, to_event__event_type__category) added.
        Baseline (before optimizations): 87 queries with 5 relationships.
        """
        status, elapsed, queries = _run_list(reverse("events"))
        print(f"\n[with relationships] {N_WITH_RELATIONS} relationships, queries={queries}, time={elapsed:.3f}s")
        assert status == 200
        assert queries <= 70, f"Expected ≤70 queries with relationships, got {queries}"

    def test_all_includes_combined(self):
        """All optional fields enabled simultaneously.
        Baseline (before optimizations): 98 queries for 25 events.
        """
        status, elapsed, queries = _run_list(
            reverse("events"),
            {"include_notes": "true", "include_files": "true", "include_details": "true"},
        )
        print(f"\n[all includes] {N_EVENTS} events, queries={queries}, time={elapsed:.3f}s")
        assert status == 200
        assert queries <= 80, f"Expected ≤80 queries with all includes, got {queries}"
