import json

import pytest

from activity.models import Event
from activity.tests import schema_examples
from revision.manager import ACTION_ADDED, ACTION_UPDATED


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventTypeRevisions:
    """Tests for ensuring EventType model correctly creates and stores revisions using the in-house revision system."""

    def test_eventtype_creation_revision(self, cat1_cat2_event_types):
        """Test that EventTypes have creation revisions."""
        event_type = cat1_cat2_event_types[0]

        # It should be the first revision, just created by the fixture
        assert event_type.revision.count() == 1
        revision = event_type.revision.first()
        assert revision.sequence == 1
        assert revision.action == ACTION_ADDED
        assert revision.data.get("display") == event_type.display
        assert revision.data.get("value") == event_type.value

    def test_schema_changes_create_revision(self, cat1_cat2_event_types):
        """Verify that changes to the schema field create proper revisions."""
        event_type = cat1_cat2_event_types[0]
        old_schema = event_type.schema

        event_type.schema = schema_examples.WILDLIFE_SCHEMA
        event_type.save()
        assert event_type.revision.count() == 2

        # revisions are ordered by sequence ascending by default
        first_revision, latest_revision = event_type.revision.all()
        assert first_revision.sequence == 1
        assert latest_revision.sequence == 2
        assert latest_revision.data.get("schema") == schema_examples.WILDLIFE_SCHEMA
        assert latest_revision.action == ACTION_UPDATED
        assert first_revision.data.get("schema") == old_schema

    def test_multiple_schema_revisions(self, cat1_cat2_event_types):
        """Verify multiple schema updates create proper revision history."""
        event_type = cat1_cat2_event_types[1]

        schemas = [
            schema_examples.WILDLIFE_SCHEMA,
            schema_examples.ET_SCHEMA,
            json.dumps(
                {
                    "json": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "testDate": {
                                "title": "Valid Date Field",
                                "type": "string",
                                "format": "date",
                                "description": "A valid date field.",
                                "deprecated": False,
                            }
                        },
                        "required": ["testDate"],
                    },
                    "ui": {"fields": {}, "headers": {}, "order": [], "sections": {}},
                }
            ),
        ]

        for schema in schemas:
            event_type.schema = schema
            event_type.save()

        assert event_type.revision.count() == len(schemas) + 1

        revisions = list(event_type.revision.all()[1:])
        for i, rev in enumerate(revisions):
            assert rev.data.get("schema") == schemas[i]

    def test_field_changes_create_revisions(self, cat1_cat2_event_types):
        """Test that updating various fields creates appropriate revisions."""

        event_type = cat1_cat2_event_types[2]
        field_updates = [
            {"field": "display", "value": "Updated Display"},
            {"field": "value", "value": "updated_value"},
            {"field": "is_active", "value": False},
            {"field": "default_priority", "value": Event.PRI_URGENT},
        ]

        for i, update in enumerate(field_updates):
            current_revision = event_type.revision.last()

            # Update the field and save
            setattr(event_type, update["field"], update["value"])
            event_type.save()

            latest_revision = event_type.revision.last()
            assert latest_revision.action == ACTION_UPDATED
            assert update["field"] in latest_revision.data
            assert latest_revision.data.get(update["field"]) == update["value"]
            assert latest_revision.sequence == current_revision.sequence + 1

            # Verify revision count has increased
            assert event_type.revision.count() == i + 2

    def test_multiple_updates_create_revision_sequence(self, cat1_cat2_categories, cat1_cat2_event_types):
        """Test that multiple updates to an EventType create properly sequenced revisions."""
        event_type = cat1_cat2_event_types[4]
        cat2 = cat1_cat2_categories[1]

        updates = [
            {"field": "display", "value": "First Update Display"},
            {"field": "value", "value": "new_value"},
            {"field": "category", "value": cat2},
        ]

        for update in updates:
            setattr(event_type, update["field"], update["value"])
            event_type.save()

        assert event_type.revision.count() == len(updates) + 1

        revisions = list(event_type.revision.all()[1:])

        for i, revision in enumerate(revisions):
            value = updates[i]["value"]
            if not isinstance(value, str):
                value = str(value.id)
            assert revision.data.get(updates[i]["field"]) == value

        sequences = [r.sequence for r in event_type.revision.all()]
        assert sequences == list(range(1, len(sequences) + 1))
