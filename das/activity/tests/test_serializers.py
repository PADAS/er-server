import logging

from django.test import TestCase

from activity.serializers.fields import (
    CoordinateField,
    PriorityField
)
from activity.serializers.patrol_serializers import (
    PatrolSerializer
)
from activity.models import Patrol, PatrolSegment


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

        PriorityField.validate(
            is_correct_data_valid
        )


class TestPatrolSerializer(TestCase):
    def test_patrol_serializer(self):
        patrol = Patrol.objects.create(
            title="Test Patrol"
        )
        PatrolSegment.objects.create(patrol=patrol)

        serializer = PatrolSerializer(instance=patrol)
        print(serializer.data)

        return
