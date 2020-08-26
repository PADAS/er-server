import json
import logging

from django.test import TestCase

from activity.serializers.fields import (
    CoordinateField,
    priority_field
)
from activity.serializers.patrol_serializers import (
    PatrolNoteSerializer,
    PatrolSerializer,
    PatrolSegmentSerializer
)
from activity.models import (
    Patrol,
    PatrolNote,
    PatrolSegment
)


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


class TestPriorityField(TestCase):
    def test_validate(self):
        is_correct_data_valid = None
        is_wrong_data_valid = None

        ps = PatrolSerializer(
            data={
                "title": "Test Patrol",
                "priority": 100000
            }
        )

        print(ps.is_valid(), ps.validated_data, ps.errors)


class TestPatrolSerializer(TestCase):
    def test_patrol_serializer(self):
        patrol = Patrol.objects.create(
            title="Test Patrol"
        )
        patrol_note = PatrolNote.objects.create(
            patrol=patrol,
            text='Hello world'
        )
        patrol_segment = PatrolSegment.objects.create(
            patrol=patrol,
            time_range={
                'lower': 'asdfdfs',
                'upper': 'asddsfdsf'
            }
        )

        serializer = PatrolNoteSerializer(instance=patrol_note)
        print('\n\nPATROL NOTE', json.dumps(serializer.data))

        serializer = PatrolSerializer(instance=patrol)
        print('\n\nPATROL', json.dumps(serializer.data))

        serializer = PatrolSegmentSerializer(instance=patrol_segment)
        print('\n\nPATROL SEGMENT', json.dumps(serializer.data))

        return
