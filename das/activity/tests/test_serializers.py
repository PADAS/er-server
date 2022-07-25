import logging
from datetime import datetime, timedelta

import jsonschema
import pytest

from django.contrib.gis.geos import Point
from django.test import TestCase

from activity.models import Patrol
from activity.serializers import EventSerializer
from activity.serializers.fields import CoordinateField
from activity.serializers.patrol_serializers import PatrolSerializer

logger = logging.getLogger(__name__)


class TestCoordinateField(TestCase):
    def test_coordinate_field_validator(self):
        CoordinateField.validate({
            'latitude': 0.00,
            'longitude': 1.00
        })

    def test_coordinate_field_to_representation(self):
        CoordinateField().to_internal_value({
            'latitude': 0.00,
            'longitude': 1.00
        })

        CoordinateField().to_representation(0)


class TestPatrolSerializer(TestCase):
    serialized_data_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string"
            },
            "created_at": {
                "type": "string"
            },
            "updated_at": {
                "type": "string"
            },
            "objective": {
                "type": "string"
            },
            "priority": {
                "type": "number"
            },
            "state": {
                "type": "string"
            },
            "title": {
                "type": "string"
            },
            "files": {
                "type": "array"
            },
            "notes": {
                "type": "array"
            },
            "patrol_segments": {
                "type": "array"
            },
            "serial_number": {
                "type": ["null", "number"]
            }
        }
    }
    objective = 'Test Patrol object'
    title = "Test Patrol"

    def __atest_data_serialization(self):
        ps = PatrolSerializer(
            data={
                'objective': self.objective,
                'title': self.title
            }
        )

        self.assertTrue(ps.is_valid())

        try:
            jsonschema.validate(ps.data, self.serialized_data_schema)
        except jsonschema.exceptions.ValidationError:
            does_serialized_data_match_schema = False
        else:
            does_serialized_data_match_schema = True

        self.assertTrue(does_serialized_data_match_schema)

    def test_instance_to_data_serialization(self):
        patrol = Patrol.objects.create(
            objective=self.objective,
            title=self.title
        )
        ps = PatrolSerializer(instance=patrol)

        try:
            jsonschema.validate(ps.data, self.serialized_data_schema)
        except jsonschema.exceptions.ValidationError:
            does_serialized_data_match_schema = False
        else:
            does_serialized_data_match_schema = True

        self.assertEqual(ps.data['title'], self.title)
        self.assertTrue(does_serialized_data_match_schema)

        # TODO move to apt TestCase classes
        # patrol_note = PatrolNote.objects.create(
        #     patrol=patrol,
        #     text='Hello world'
        # )
        # patrol_type = PatrolType.objects.create(
        #     display='Patrol Type 112233',
        #     value='patrol-type-112233'
        # )
        # patrol_segment = PatrolSegment.objects.create(
        #     patrol=patrol,
        #     patrol_type=patrol_type
        # )
        #
        # patrol_note_serializer = PatrolNoteSerializer(instance=patrol_note)
        #
        # patrol_serializer = PatrolSerializer(instance=patrol)

        # patrol_segment_serializer = PatrolSegmentSerializer(data={
        #     'patrol': patrol_serializer.data,
        #     'patrol_type': patrol_type,
        #     'start_date': '2000-01-01T00:00:00',
        #     'end_date': datetime.datetime(2020, 12, 31, 23, 59, 59)
        # })

        # patrol_segment_serializer = PatrolSegmentSerializer(
        #     instance=patrol_segment
        # )
        #
        # print(
        #     '\n\nPATROL SEGMENT',
        #     # patrol_segment_serializer.is_valid(),
        #     # patrol_segment_serializer.errors,
        #     json.dumps(patrol_segment_serializer.data)
        # )


@pytest.mark.django_db
class TestEventSerializer:
    # TODO Pending some fields like files, updates, as they are part of nested serializers or other methods.
    def test_serialized_event(self, event_with_detail, five_event_notes):
        now = datetime.now()
        event = event_with_detail.event
        event.message = "Houston, we have had a problem here"
        event.comment = "It is a trap"
        event.title = "Accident at moon"
        event.event_time = now
        event.end_time = now + timedelta(hours=2)
        event.provenance = "staff"
        event.location = Point(-103.313486, 20.420935)
        event.save()
        event_with_detail.data = {
            "event_details": {
                "type_accident": "Crash car",
                "animals_involved": "4",
                "number_people_involved": 2,
            }
        }
        event_with_detail.save()
        for note in five_event_notes:
            note.event = event
            note.save()

        event.refresh_from_db()
        serialized_event = EventSerializer(event).data

        assert serialized_event["id"] == str(event.id)
        assert serialized_event["message"] == event.message
        assert serialized_event["comment"] == event.comment
        assert serialized_event["title"] == event.title
        assert serialized_event["state"] == event.state
        assert serialized_event["time"] == event.time.astimezone().isoformat()
        assert serialized_event["end_time"] == event.end_time.astimezone(
        ).isoformat()
        assert serialized_event["provenance"] == event.provenance
        assert serialized_event["event_type"] == event.event_type.value
        assert serialized_event["event_details"] == event_with_detail.data.get(
            "event_details"
        )
        assert serialized_event["location"] == {
            "latitude": 20.420935,
            "longitude": -103.313486,
        }
        assert serialized_event["priority"] == 0
        assert serialized_event["priority_label"] == "Gray"
        assert serialized_event["attributes"] == {}
        assert len(serialized_event["notes"]) == 5
        assert serialized_event["is_contained_in"] == []
        assert serialized_event["files"] == []
        assert serialized_event["related_subjects"] == []
        assert serialized_event["patrol_segments"] == []
        assert serialized_event["is_collection"] is False
        assert serialized_event["patrols"] == []
