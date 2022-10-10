import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import jsonschema
import pytest

from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase

from activity.libs import constants as activities_constants
from activity.models import Event, EventGeometry, EventType, Patrol
from activity.serializers import DuplicateResourceError, EventSerializer
from activity.serializers.fields import CoordinateField
from activity.serializers.geometries import EventGeometryRevisionSerializer
from activity.serializers.patrol_serializers import PatrolSerializer


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

    def test_serialized_geometry_of_event_with_both_location_and_geometry(self, event_geometry_with_polygon, monkeypatch, rf, ops_user):
        ops_user.is_superuser = True
        ops_user.save()
        event = event_geometry_with_polygon.event
        event.location = Point(-103.313486, 20.420935)
        event.save()
        request = MagicMock()
        request.build_absolute_uri = MagicMock()

        serialized_event = EventSerializer(
            event, context=self._get_context(request, ops_user)).data

        assert len(serialized_event["geometry"]["features"]) == 1
        assert serialized_event["geometry"]["features"][0]["geometry"]["type"] == "Polygon"

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

    def test_create_event_with_geometry_using_a_feature(self, event_type, rf, admin_user):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
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

    def test_create_event_with_geometry_using_a_feature_collection(
            self, event_type, rf, admin_user
    ):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
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

    def test_create_event_with_default_priority_and_state(self, rf, monkeypatch, ops_user, event_type):
        monkeypatch.user = ops_user

        serialized = EventSerializer(
            data={
                "title": "Title",
                "event_type": event_type.value
            },
            context=self._get_context(rf, ops_user)
        )
        serialized.is_valid()
        event = serialized.save()

        assert event.priority == event_type.default_priority
        assert event.state == event_type.default_state

    def test_create_event_with_custom_priority_and_state(self, rf, monkeypatch, ops_user, event_type):
        monkeypatch.user = ops_user

        serialized = EventSerializer(
            data={
                "title": "Title",
                "event_type": event_type.value,
                "priority": 100,
                "state": "active"
            },
            context=self._get_context(rf, ops_user)
        )
        serialized.is_valid()
        event = serialized.save()

        assert event.priority == 100
        assert event.state == "active"

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

    def test_create_event_with_geometry_using_wrong_feature_handler_exception(self, rf, admin_user, event_type):
        data = {
            "event_type": event_type.value,
            "title": "Title",
            "geometry": self.wrong_feature,
        }

        serialized_event = EventSerializer(
            data=data, context=self._get_context(rf, admin_user))

        assert not serialized_event.is_valid()

    def test_create_event_with_geometry_using_wrong_feature_collection_handler_exception(self, rf, admin_user, event_type):
        data = {
            "event_type": event_type.value,
            "title": "Title",
            "geometry": self.wrong_feature_collection,
        }

        serialized_event = EventSerializer(
            data=data, context=self._get_context(rf, admin_user))

        assert not serialized_event.is_valid()

    def test_validation_when_saving_point_for_events_type_with_polygon_geometry_type(self, rf, monkeypatch, event_type, ops_user):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        monkeypatch.user = ops_user

        serialized = EventSerializer(
            data={
                "location": {
                    "latitude": 41.8568816599531,
                    "longitude": -105.61289437001126,
                },
                "event_type": event_type.value,
                "title": "Title",
            },
            context=self._get_context(rf, ops_user)
        )

        assert not serialized.is_valid()
        assert "location" in serialized.errors
        assert serialized.errors["location"][0] == "This field is not allowed for events with polygon type."

    def test_validation_when_saving_polygon_for_events_type_with_point_geometry_type(self, rf, monkeypatch, event_type, ops_user):
        event_type.geometry_type = EventType.GeometryTypesChoices.POINT
        event_type.save()
        monkeypatch.user = ops_user

        serialized = EventSerializer(
            data={
                "geometry": {
                    "type": "Feature",
                    "properties": {
                        "size": 10,
                        "large": 20
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [
                                    -103.42475652694702,
                                    20.621970067076848
                                ],
                                [
                                    -103.42286825180052,
                                    20.624661133427434
                                ],
                                [
                                    -103.42717051506042,
                                    20.623235275838002
                                ],
                                [
                                    -103.42475652694702,
                                    20.621970067076848
                                ]
                            ]
                        ]
                    }
                },
                "event_type": event_type.value,
                "title": "Title",
            },
            context=self._get_context(rf, ops_user)
        )

        assert not serialized.is_valid()
        assert "geometry" in serialized.errors
        assert serialized.errors["geometry"][0] == "This field is not allowed for events with point type."

    def test_validation_when_end_time_is_lower_than_instance_saved(self, rf, monkeypatch, event_with_detail, ops_user):
        event = event_with_detail.event
        end_time = event.time - timedelta(hours=1)
        monkeypatch.user = ops_user

        serialized = EventSerializer(instance=event, data={
                                     "end_time": end_time}, context=self._get_context(rf, ops_user))

        assert not serialized.is_valid()
        assert "non_field_errors" in serialized.errors
        assert serialized.errors["non_field_errors"][0] == "Event end_time must not be earlier than event time."

    def test_validation_when_not_event_type_in_payload(self, rf, ops_user, monkeypatch):
        monkeypatch.user = ops_user

        serialized = EventSerializer(
            data={
                "title": "Title"
            },
            context={"request": monkeypatch}
        )

        assert not serialized.is_valid()
        assert "event_type" in serialized.errors
        assert serialized.errors["event_type"][0] == "Event type must be provided."

    def test_validation_when_not_event_type_in_payload_and_not_in_event_source(self, rf, ops_user, monkeypatch, event_source):
        monkeypatch.user = ops_user
        event_source.eventprovider.owner = ops_user
        event_source.eventprovider.save()

        serialized = EventSerializer(
            data={
                "title": "Title",
                "eventsource": event_source.id
            },
            context=self._get_context(rf, ops_user)
        )

        assert not serialized.is_valid()
        assert "event_type" in serialized.errors
        assert serialized.errors["event_type"][0] == "Event type must be provided."

    def test_validation_duplicated_event_source_event(self, rf, monkeypatch, ops_user, event_source, event_type, event_source_event):
        monkeypatch.user = ops_user
        event_source.eventprovider.owner = ops_user
        event_source.eventprovider.save()
        event_source_event.external_event_id = "this"
        event_source_event.eventsource = event_source
        event_source_event.save()

        serialized = EventSerializer(
            data={
                "title": "Title",
                "event_type": event_type.value,
                "eventsource": event_source.id,
                "external_event_id": "this"
            },
            context=self._get_context(rf, ops_user)
        )

        with pytest.raises(DuplicateResourceError):
            serialized.is_valid()

    def _get_context(self, request, user):
        request.user = user
        return {"request": request}


@pytest.mark.django_db
class TestEventGeometrySerializer:
    def test_serialized_event_geometry_updates_format(
        self, event_geometry_with_polygon
    ):
        serialized_event_geometry_revision = EventGeometryRevisionSerializer(
            event_geometry_with_polygon.revision.last()
        ).data

        assert isinstance(serialized_event_geometry_revision["message"], str)
        assert isinstance(serialized_event_geometry_revision["time"], str)
        assert isinstance(serialized_event_geometry_revision["type"], str)
        assert isinstance(serialized_event_geometry_revision["user"], dict)

    def test_serialized_event_geometry_updates(self, event_geometry_with_polygon):
        event_geometry_revision = event_geometry_with_polygon.revision.last()
        serialized_event_geometry_revision = EventGeometryRevisionSerializer(
            event_geometry_revision
        ).data

        assert serialized_event_geometry_revision["message"] == "Added"
        assert (
            serialized_event_geometry_revision["time"]
            == event_geometry_revision.revision_at.isoformat()
        )
        assert serialized_event_geometry_revision["type"] == "add_eventgeometry"
        assert serialized_event_geometry_revision["user"] == {
            "first_name": "",
            "last_name": "",
            "username": "",
        }

    def test_serialized_event_geometry_updates_properties(
        self, event_geometry_with_polygon
    ):
        event_geometry_with_polygon.properties = {"key": "value"}
        event_geometry_with_polygon.save()
        event_geometry_revisions = event_geometry_with_polygon.revision.all()
        latest_event_geometry_revision = event_geometry_with_polygon.revision.order_by(
            "-sequence"
        )[0]

        serialized_event_geometry_revision = EventGeometryRevisionSerializer(
            event_geometry_revisions, many=True
        ).data

        assert serialized_event_geometry_revision[1]["message"] == "Updated"
        assert (
            serialized_event_geometry_revision[1]["time"]
            == latest_event_geometry_revision.revision_at.isoformat()
        )
        assert serialized_event_geometry_revision[1]["type"] == "update_properties"
        assert serialized_event_geometry_revision[1]["user"] == {
            "first_name": "",
            "last_name": "",
            "username": "",
        }

    def test_serialized_event_geometry_updates_geometry(
        self, event_geometry_with_polygon
    ):
        event_geometry_with_polygon.geometry = Polygon(
            (
                (-103.41898441314697, 20.638567565077864),
                (-103.41387748718262, 20.63499318125139),
                (-103.40585231781006, 20.646840535793658),
                (-103.41898441314697, 20.638567565077864),
            )
        )
        event_geometry_with_polygon.save()
        event_geometry_revisions = event_geometry_with_polygon.revision.all()
        latest_event_geometry_revision = event_geometry_with_polygon.revision.order_by(
            "-sequence"
        )[0]

        serialized_event_geometry_revision = EventGeometryRevisionSerializer(
            event_geometry_revisions, many=True
        ).data

        assert serialized_event_geometry_revision[1]["message"] == "Updated"
        assert (
            serialized_event_geometry_revision[1]["time"]
            == latest_event_geometry_revision.revision_at.isoformat()
        )
        assert serialized_event_geometry_revision[1]["type"] == "update_geometry"
        assert serialized_event_geometry_revision[1]["user"] == {
            "first_name": "",
            "last_name": "",
            "username": "",
        }
