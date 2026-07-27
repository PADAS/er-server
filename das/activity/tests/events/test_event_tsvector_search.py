"""ERA-13500: the event search vector must not index the event type's schema.

Before the fix, ``tsvector_doc_trigger`` / ``tsvector_event_title_trigger``
folded ``et.schema::text`` into ``tsvector_event``, so every choice label a
schema *could* offer matched a text search on every event of that type --
searching one rhino's name returned sightings of all the others.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from django.db import connection

from activity.models import Event, EventType
from activity.tsvector_rebuild import rebuild_event_tsvectors
from factories import EventDetailsFactory, EventFactory, EventTypeFactory

# The customer-reported term: a choice option in the schema, not on the event.
SCHEMA_ONLY_TERM = "mokgadi"
# A second choice option, the one actually selected on the event.
SELECTED_TERM = "thandi"
# Unique enough that a --reuse-db leftover event cannot collide with it.
EVENT_TYPE_DISPLAY_TERM = "rhinowatch"
# Wording that only ever appears in the schema's property title.
SCHEMA_PROPERTY_TITLE_TERM = "zindaba"


def _rhino_schema() -> str:
    return json.dumps(
        {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "properties": {
                    "rhino_name": {
                        "type": "string",
                        "title": f"{SCHEMA_PROPERTY_TITLE_TERM.title()} Individual",
                        "enum": [SCHEMA_ONLY_TERM, SELECTED_TERM],
                        "enumNames": {SCHEMA_ONLY_TERM: "Mokgadi", SELECTED_TERM: "Thandi"},
                    },
                },
            },
            "definition": ["rhino_name"],
        }
    )


def _tsvector_event(event_id: uuid.UUID) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT tsvector_event::text FROM activity_tsvectormodel WHERE event_id = %s", [str(event_id)])
        row = cursor.fetchone()
    return row[0] if row else None


def _poison_with_schema_term(event_id: uuid.UUID) -> None:
    """Recreate a pre-fix row: schema text welded into the vector at weight B."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE activity_tsvectormodel ts
            SET tsvector_event = coalesce(ts.tsvector_event, ''::tsvector) ||
                                 setweight(to_tsvector(et.schema::text), 'B')
            FROM activity_event e
                     JOIN activity_eventtype et ON et.id = e.event_type_id
            WHERE ts.event_id = e.id
              AND e.id = %s
            """,
            [str(event_id)],
        )


def _matching_ids(search_text: str) -> set[uuid.UUID]:
    return set(Event.objects.by_text_filter(search_text).values_list("id", flat=True))


@pytest.fixture
def rhino_event_type(das_tenant_monkeypatch: Any) -> EventType:
    return EventTypeFactory(
        value=f"rhino_sighting_{uuid.uuid4().hex[:8]}",
        display=f"{EVENT_TYPE_DISPLAY_TERM.title()} Sighting",
        schema=_rhino_schema(),
    )


@pytest.fixture
def event_without_schema_term(rhino_event_type: EventType) -> Event:
    """Event of a type whose schema offers "mokgadi", with "thandi" selected."""
    event = EventFactory(event_type=rhino_event_type, title="Sighting near the dam")
    EventDetailsFactory(event=event, data={"event_details": {"rhino_name": SELECTED_TERM}})
    return event


@pytest.fixture
def event_with_schema_term(rhino_event_type: EventType) -> Event:
    """Event that genuinely has "mokgadi" in its details."""
    event = EventFactory(event_type=rhino_event_type, title="Sighting near the ridge")
    EventDetailsFactory(event=event, data={"event_details": {"rhino_name": SCHEMA_ONLY_TERM}})
    return event


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTsvectorExcludesEventTypeSchema:
    def test_schema_only_choice_option_does_not_match_text_search(self, event_without_schema_term: Event) -> None:
        assert event_without_schema_term.id not in _matching_ids(SCHEMA_ONLY_TERM)

    def test_choice_option_present_in_event_details_matches_text_search(self, event_with_schema_term: Event) -> None:
        assert event_with_schema_term.id in _matching_ids(SCHEMA_ONLY_TERM)

    def test_only_the_event_that_selected_the_option_is_returned(
        self, event_with_schema_term: Event, event_without_schema_term: Event
    ) -> None:
        matches = _matching_ids(SCHEMA_ONLY_TERM)

        assert event_with_schema_term.id in matches
        assert event_without_schema_term.id not in matches

    def test_event_type_display_name_still_matches_text_search(self, event_without_schema_term: Event) -> None:
        assert event_without_schema_term.id in _matching_ids(EVENT_TYPE_DISPLAY_TERM)

    def test_event_title_still_matches_text_search(self, event_without_schema_term: Event) -> None:
        assert event_without_schema_term.id in _matching_ids("dam")

    def test_schema_property_titles_do_not_match_text_search(self, event_without_schema_term: Event) -> None:
        # The property's title wording is schema metadata, never event content.
        assert event_without_schema_term.id not in _matching_ids(SCHEMA_PROPERTY_TITLE_TERM)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTitleUpdateRebuildsTsvector:
    def test_title_update_keeps_schema_terms_out_of_the_vector(self, event_without_schema_term: Event) -> None:
        Event.objects.filter(id=event_without_schema_term.id).update(title="Renamed kifaru report")

        vector = _tsvector_event(event_without_schema_term.id)

        assert vector is not None
        assert "kifaru" in vector
        assert SCHEMA_ONLY_TERM not in vector

    def test_title_update_makes_the_new_title_searchable(self, event_without_schema_term: Event) -> None:
        Event.objects.filter(id=event_without_schema_term.id).update(title="Renamed kifaru report")

        assert event_without_schema_term.id in _matching_ids("kifaru")

    def test_title_update_does_not_resurrect_schema_terms_on_a_poisoned_row(
        self, event_without_schema_term: Event
    ) -> None:
        _poison_with_schema_term(event_without_schema_term.id)
        assert SCHEMA_ONLY_TERM in (_tsvector_event(event_without_schema_term.id) or "")

        Event.objects.filter(id=event_without_schema_term.id).update(title="Renamed kifaru report")

        assert SCHEMA_ONLY_TERM not in (_tsvector_event(event_without_schema_term.id) or "")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestRebuildEventTsvectors:
    """Covers activity.tsvector_rebuild.rebuild_event_tsvectors (all-tenants walk)."""

    def test_rebuild_strips_schema_terms_from_existing_rows(self, event_without_schema_term: Event) -> None:
        _poison_with_schema_term(event_without_schema_term.id)
        assert event_without_schema_term.id in _matching_ids(SCHEMA_ONLY_TERM)

        rebuild_event_tsvectors(connection)

        assert event_without_schema_term.id not in _matching_ids(SCHEMA_ONLY_TERM)

    def test_rebuild_preserves_title_details_and_event_type_terms(
        self, event_with_schema_term: Event, event_without_schema_term: Event
    ) -> None:
        _poison_with_schema_term(event_without_schema_term.id)

        rebuild_event_tsvectors(connection)

        assert event_without_schema_term.id in _matching_ids("dam")
        assert event_without_schema_term.id in _matching_ids(EVENT_TYPE_DISPLAY_TERM)
        assert event_without_schema_term.id in _matching_ids(SELECTED_TERM)
        assert event_with_schema_term.id in _matching_ids(SCHEMA_ONLY_TERM)

    def test_rebuild_uses_the_latest_event_details_row(self, rhino_event_type: EventType) -> None:
        event = EventFactory(event_type=rhino_event_type, title="Sighting at the crossing")
        EventDetailsFactory(event=event, data={"event_details": {"rhino_name": SELECTED_TERM}})
        EventDetailsFactory(event=event, data={"event_details": {"rhino_name": SCHEMA_ONLY_TERM}})

        rebuild_event_tsvectors(connection)

        vector = _tsvector_event(event.id)
        assert vector is not None
        assert SCHEMA_ONLY_TERM in vector
        assert SELECTED_TERM not in vector

    def test_rebuild_leaves_a_vector_for_an_event_with_no_details_row(self, rhino_event_type: EventType) -> None:
        # No EventDetails means no trigger fired, so seed the row the way the
        # pre-fix trigger would have and check the rebuild does not null it out.
        event = EventFactory(event_type=rhino_event_type, title="Sighting with no details")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO activity_tsvectormodel (id, event_id, das_tenant_id, tsvector_event)
                SELECT %s, e.id, e.das_tenant_id, setweight(to_tsvector(et.schema::text), 'B')
                FROM activity_event e
                         JOIN activity_eventtype et ON et.id = e.event_type_id
                WHERE e.id = %s
                """,
                [str(uuid.uuid4()), str(event.id)],
            )

        rebuild_event_tsvectors(connection)

        vector = _tsvector_event(event.id)
        assert vector is not None
        assert "detail" in vector  # from the title
        assert SCHEMA_ONLY_TERM not in vector

    def test_rebuild_walks_every_row_when_batches_are_smaller_than_the_table(self, rhino_event_type: EventType) -> None:
        events = []
        for index in range(3):
            event = EventFactory(event_type=rhino_event_type, title=f"Batch walk sighting {index}")
            EventDetailsFactory(event=event, data={"event_details": {"rhino_name": SELECTED_TERM}})
            _poison_with_schema_term(event.id)
            events.append(event)

        rows_updated = rebuild_event_tsvectors(connection, batch_size=1)

        assert rows_updated >= len(events)
        matches = _matching_ids(SCHEMA_ONLY_TERM)
        for event in events:
            assert event.id not in matches
