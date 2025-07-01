"""
Integration tests for EventType workflows.

Tests the complete workflow of:
1. EventType creation with reference schemas (subjects, users, choices, etc.)
2. Schema rendering and validation
3. Event creation using those EventTypes
4. End-to-end data validation
"""

import json
import os

import pytest

from django.urls import reverse
from rest_framework import status

from activity.models import Event, EventType


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypeWorkflows:
    """
    Integration tests for EventType end-to-end workflows.
    Tests the complete pipeline: EventType creation → Schema rendering → Event creation → Data verification,
    with focus on choice field reference resolution and data integrity.
    """

    # Test data configurations for parameterized workflow testing
    WORKFLOW_TEST_PARAMS = [
        (
            "subjects_single_choice.json",
            "subjects_single_test",
            {"subjects_from_subject_group": "550e8400-e29b-41d4-a716-446655440000"},
        ),
        (
            "subjects_multiple_choice.json",
            "multiple_subjects_fire",
            {
                "subjects_from_subject_group": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "660e8400-e29b-41d4-a716-446655440001",
                ]
            },
        ),
        ("users_choice.json", "users_test", {"user": "123e4567-e89b-12d3-a456-426614174000"}),
        ("choice_list.json", "choice_list_test", {"choice_list_of_choices": "active"}),
        (
            "complex_mixed.json",
            "complex_test",
            {
                "incident_description": "Sample incident description",
                "estimated_count": 42,
                "affected_subjects": ["550e8400-e29b-41d4-a716-446655440000"],
                "priority_level": "high",
            },
        ),
    ]
    WORKFLOW_TEST_IDS = [
        "Single choice subject selection by group",
        "Subjects Multiple Choice",
        "User selection",
        "Existing choice list selection",
        "Complex mixed schema with multiple field types",
    ]

    def load_json_fixture(self, filename):
        """Load JSON workflow schema fixture file."""
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "workflow_schemas", filename)
        with open(fixture_path, "r") as f:
            return json.load(f)

    def create_event_type_with_schema(self, client, schema, value="test_workflow", category=None):
        """Create an EventType with the given schema."""
        url = reverse("v2-eventtype-list")
        data = {
            "value": value,
            "display": f"Test EventType {value}",
            "category": category.value if category else "security",
            "schema": schema,
            "is_active": True,
        }
        response = client.post(url, data=data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        return EventType.objects.get(value=value)

    def get_rendered_schema(self, client, event_type):
        """Get rendered schema for an EventType."""
        url = reverse("v2-eventtype-retrieve-schema", kwargs={"eventtype_value": event_type.value})
        response = client.get(url, {"pre_render": True})
        assert response.status_code == status.HTTP_200_OK
        return response.json()

    def create_event_with_data(self, client, event_type, attributes_data):
        """Create an event with event_details data."""
        url = reverse("events")
        data = {
            "event_type": event_type.value,
            "message": f"Test event for {event_type.value}",
            "event_details": attributes_data,
        }
        response = client.post(url, data=data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        response_data = response.json()
        # Event data is nested under 'data' key in the response
        event_id = response_data["data"]["id"]
        event = Event.objects.get(id=event_id)
        return event, response_data["data"]

    @pytest.mark.parametrize("schema_filename,event_type_value,test_data", WORKFLOW_TEST_PARAMS, ids=WORKFLOW_TEST_IDS)
    def test_eventtype_workflow_parameterized(
        self,
        superuser_client,
        cat1_cat2_categories,
        schema_filename,
        event_type_value,
        test_data,
    ):
        """Parameterized test for EventType end-to-end workflows.

        Tests the complete pipeline: EventType creation → Schema rendering → Event creation → Data verification
        across different reference schema types and field configurations.
        """

        schema = self.load_json_fixture(schema_filename)

        # First phase: EventType creation
        event_type = self.create_event_type_with_schema(
            superuser_client, schema, event_type_value, cat1_cat2_categories[0]
        )

        assert event_type.value == event_type_value
        assert json.loads(event_type.schema) == schema

        # Second phase: Schema rendering
        rendered_schema = self.get_rendered_schema(superuser_client, event_type)

        assert "json" in rendered_schema
        assert "ui" in rendered_schema
        assert "$ref" not in json.dumps(rendered_schema["json"])

        # Third phase: Event creation
        event, response_data = self.create_event_with_data(superuser_client, event_type, test_data)

        assert event.event_type == event_type

        # Fourth phase: Verify end-to-end data integrity
        for field_name, expected_value in test_data.items():
            assert response_data["event_details"][field_name] == expected_value

            if isinstance(expected_value, list):
                assert len(response_data["event_details"][field_name]) == len(expected_value)

        event_details = event.event_details.first()
        assert event_details is not None
        for field_name, expected_value in test_data.items():
            assert event_details.data["event_details"][field_name] == expected_value
