from __future__ import annotations

import json

import pytest

from activity.models import Event, EventDetails, EventType
from activity.serializers.event_details import EventDetailsSerializer
from activity.tests.helpers.schema_test_utils import V1_DRAFT, V2SchemaBuilder
from factories import EventTypeFactory

CHECKBOX_FIELD = "unknownpicklist"


@pytest.fixture
def v1_checkbox_event_type(cat1_cat2_categories):
    cat1, _ = cat1_cat2_categories
    schema = {
        "schema": {
            "$schema": V1_DRAFT,
            "title": "Test Schema",
            "type": "object",
            "properties": {CHECKBOX_FIELD: {"key": CHECKBOX_FIELD}},
        },
        "definition": [
            {
                "key": CHECKBOX_FIELD,
                "type": "checkboxes",
                "title": "Unknown",
                "titleMap": [
                    {"value": "unknown_rhino_1", "name": "Unknown Rhino 1"},
                    {"value": "unknown_rhino_2", "name": "Unknown Rhino 2"},
                ],
            }
        ],
    }
    return EventTypeFactory.create(
        category=cat1,
        value="rhino_sighting_v1",
        schema=json.dumps(schema),
        version=EventType.VersionChoices.VERSION_1,
    )


@pytest.fixture
def v1_event_with_checkbox_details(v1_checkbox_event_type, admin_user):
    event = Event.objects.create(
        title="Test rhino sighting",
        event_type=v1_checkbox_event_type,
        created_by_user=admin_user,
        state="new",
    )
    details = EventDetails.objects.create(
        event=event,
        data={"event_details": {CHECKBOX_FIELD: ["unknown_rhino_1"]}},
    )
    return event, details


@pytest.fixture
def v2_event_type_with_fields(cat1_cat2_categories):
    cat1, _ = cat1_cat2_categories
    schema = V2SchemaBuilder.simple_field("species", "string")
    schema["json"]["properties"]["location_name"] = {
        "type": "string",
        "title": "Location Name",
        "deprecated": False,
    }
    return EventTypeFactory.create(
        category=cat1,
        value="wildlife_sighting_v2",
        schema=json.dumps(schema),
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def v2_event_with_details(v2_event_type_with_fields, admin_user):
    event = Event.objects.create(
        title="Test sighting",
        event_type=v2_event_type_with_fields,
        created_by_user=admin_user,
        state="new",
    )
    details = EventDetails.objects.create(
        event=event,
        data={"event_details": {"species": "elephant", "location_name": "North Ridge"}},
    )
    return event, details


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestV2EventDetailsUpdates:
    """Verify that v2-schema-linked events produce event_details update history on par with v1."""

    def test_render_updates_returns_creation_entry(self, v2_event_with_details):
        _, details = v2_event_with_details
        serializer = EventDetailsSerializer(details, context={"include_updates": True})
        updates = serializer.data.get("updates", [])

        assert len(updates) >= 1
        creation = updates[-1]
        assert "Created with fields:" in creation["message"]
        assert "Species" in creation["message"]

    def test_render_updates_after_field_change(self, v2_event_with_details):
        event, details = v2_event_with_details
        details.data = {"event_details": {"species": "rhino", "location_name": "North Ridge"}}
        details.save()

        serializer = EventDetailsSerializer(details, context={"include_updates": True})
        updates = serializer.data.get("updates", [])

        assert len(updates) >= 2
        latest = updates[-1]
        assert "Species" in latest["message"]
        assert "Location Name" not in latest["message"]

    def test_render_updates_empty_when_excluded(self, v2_event_with_details):
        _, details = v2_event_with_details
        serializer = EventDetailsSerializer(details, context={"include_updates": False})
        updates = serializer.data.get("updates", [])

        assert updates == []

    def test_update_entry_has_expected_keys(self, v2_event_with_details):
        _, details = v2_event_with_details
        serializer = EventDetailsSerializer(details, context={"include_updates": True})
        updates = serializer.data.get("updates", [])

        assert len(updates) >= 1
        entry = updates[0]
        assert "message" in entry
        assert "time" in entry
        assert "user" in entry
        assert "type" in entry


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestRenderUpdatesWithNullCheckboxValue:
    """Regression test for ERA-13744: a v1 checkbox field revisioned to a null value

    used to raise TypeError: 'NoneType' object is not iterable from
    handle_checkboxes_in_fieldsets when rendering event_details update history.
    """

    def test_render_updates_does_not_raise_when_checkbox_value_is_null(self, v1_event_with_checkbox_details):
        _, details = v1_event_with_checkbox_details
        details.data = {"event_details": {CHECKBOX_FIELD: None}}
        details.save()

        serializer = EventDetailsSerializer(details, context={"include_updates": True})
        updates = serializer.data["updates"]

        assert isinstance(updates, list)
        assert len(updates) >= 2
