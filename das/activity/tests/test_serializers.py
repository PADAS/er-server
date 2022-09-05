import json
import logging
from datetime import datetime, timedelta

import jsonschema
import pytest

from django.contrib.gis.geos import Point
from django.test import TestCase

from activity.libs import constants as activities_constants
from activity.models import Event, EventGeometry, Patrol
from activity.serializers import EventSerializer
from activity.serializers.fields import CoordinateField
from activity.serializers.patrol_serializers import PatrolSerializer
from utils.features import features

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
    feature = {
        "type": "Feature",
        "properties": {"size": 10, "large": 20},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-121.77246093750001, 47.96050238891509],
                    [-118.037109375, 32.879587173066305],
                    [-83.75976562499999, 30.826780904779774],
                    [-84.5947265625, 45.1510532655634],
                    [-95.5810546875, 48.719961222646276],
                    [-121.77246093750001, 47.96050238891509],
                ]
            ],
        },
    }
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"size": 45, "large": 55, "color": "green"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-103.64158630371094, 20.67037186452816],
                            [-103.64398956298828, 20.652382371230658],
                            [-103.63197326660155, 20.653667405666592],
                            [-103.64158630371094, 20.67037186452816],
                        ]
                    ],
                },
            }
        ],
    }
    wrong_feature = {
        "type": "Feature",
        "properties": {"size": 10, "large": 20},
        "geometry": {
            "type": "Unknown",
            "coordinates": [
                [
                    [-121.77246093750001, 47.96050238891509],
                    [-118.037109375, 32.879587173066305],
                    [-83.75976562499999, 30.826780904779774],
                    [-84.5947265625, 45.1510532655634],
                    [-95.5810546875, 48.719961222646276],
                    [-121.77246093750001, 47.96050238891509],
                ]
            ],
        },
    }
    wrong_feature_collection = {

    }

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

    def test_serialized_event_with_external_sources(self, event_with_event_source_event):
        serialized_event = EventSerializer(event_with_event_source_event).data

        assert "external_source" in serialized_event
        assert serialized_event["external_source"]["url"] == activities_constants.EventTestsConstants.url
        assert serialized_event["external_source"]["icon_url"] == activities_constants.EventTestsConstants.icon_url

    def test_serialized_event_without_external_source(self, base_event):
        serialized_event = EventSerializer(base_event).data

        assert "external_source" not in serialized_event

    def test_serialized_event_without_external_sources_and_provider(self, event_with_event_source_event):
        event_source = event_with_event_source_event.eventsource_event_refs.first().eventsource
        event_source.eventprovider = None
        event_source.save(update_fields=["eventprovider"])

        serialized_event = EventSerializer(event_with_event_source_event).data

        assert "external_source" not in serialized_event

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_create_event_with_geometry_using_a_feature(self, event_type, rf, admin_user):
        data = {
            "event_type": event_type.value,
            "title": "Title",
            "geometry": self.feature,
        }

        serialized_event = EventSerializer(
            data=data, context=self._get_context(rf, admin_user))
        serialized_event.is_valid()
        serialized_event.save()

        assert Event.objects.all()
        assert EventGeometry.objects.all()

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_create_event_with_geometry_using_a_feature_collection(
            self, event_type, rf, admin_user
    ):
        data = {
            "event_type": event_type.value,
            "title": "Title",
            "geometry": self.feature_collection,
        }

        serialized_event = EventSerializer(
            data=data, context=self._get_context(rf, admin_user))
        serialized_event.is_valid()
        serialized_event.save()

        assert Event.objects.all()
        assert EventGeometry.objects.all()

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_edit_event_with_geometry_using_a_feature(self, rf, admin_user, event_geometry_with_polygon):
        event = event_geometry_with_polygon.event

        serialized_event = EventSerializer(instance=event, data={
                                           "geometry": self.feature}, context=self._get_context(rf, admin_user))
        serialized_event.is_valid()
        serialized_event.save()
        event_geometry_with_polygon.refresh_from_db()

        assert json.loads(
            event_geometry_with_polygon.geometry.geojson) == self.feature["geometry"]
        assert EventGeometry.objects.count() == 1

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_edit_event_with_geometry_using_a_feature_collection(self, rf, admin_user, event_geometry_with_polygon):
        event = event_geometry_with_polygon.event

        serialized_event = EventSerializer(instance=event, data={
                                           "geometry": self.feature_collection}, context=self._get_context(rf, admin_user))
        serialized_event.is_valid()
        serialized_event.save()
        event_geometry_with_polygon.refresh_from_db()

        assert json.loads(
            event_geometry_with_polygon.geometry.geojson) == self.feature_collection["features"][0]["geometry"]
        assert EventGeometry.objects.count() == 1

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_create_event_with_geometry_using_wrong_feature_handler_exception(self, rf, admin_user, event_type):
        data = {
            "event_type": event_type.value,
            "title": "Title",
            "geometry": self.wrong_feature,
        }

        serialized_event = EventSerializer(
            data=data, context=self._get_context(rf, admin_user))

        assert not serialized_event.is_valid()

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_create_event_with_geometry_using_wrong_feature_collection_handler_exception(self, rf, admin_user, event_type):
        data = {
            "event_type": event_type.value,
            "title": "Title",
            "geometry": self.wrong_feature_collection,
        }

        serialized_event = EventSerializer(
            data=data, context=self._get_context(rf, admin_user))

        assert not serialized_event.is_valid()

    def _get_context(self, request, user):
        request.user = user
        return {"request": request}
