import datetime
import json
import logging

from django.test import TestCase
import jsonschema
from rest_framework.exceptions import ValidationError

from activity.serializers.fields import (
    CoordinateField,
    patrol_state_field,
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
    PatrolSegment,
    PatrolType,
)
from activity.models import (
    PATROL_STATE_CHOICES,
    PC_ACTIVE,
    PRI_NONE,
    PRIORITY_CHOICES,
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


class TestPatrolStateField(TestCase):
    custom_choices = (
        (0, 'Zero'),
        (1, 'One'),
        (2, 'Two')
    )
    custom_default_parameter = 2
    default_choices = PATROL_STATE_CHOICES
    default_default_parameter = PC_ACTIVE

    def test_custom_choices(self):
        psf = patrol_state_field(choices=self.custom_choices)
        self.assertEqual(
            tuple(psf.choices.items()),
            self.custom_choices
        )
        self.assertNotEqual(
            tuple(psf.choices.items()),
            self.default_choices
        )

    def test_custom_default_parameter(self):
        psf = patrol_state_field(default=self.custom_default_parameter)
        self.assertEqual(
            psf.default,
            self.custom_default_parameter
        )
        self.assertNotEqual(
            psf.default,
            self.default_default_parameter
        )

    def test_default_choices(self):
        psf = patrol_state_field()
        self.assertEqual(
            tuple(psf.choices.items()),
            self.default_choices
        )
        self.assertNotEqual(
            tuple(psf.choices.items()),
            self.custom_choices
        )

    def test_default_default_parameter(self):
        psf = patrol_state_field()
        self.assertEqual(
            psf.default,
            self.default_default_parameter
        )
        self.assertNotEqual(
            psf.default,
            self.custom_default_parameter
        )

    def test_validation(self):
        correct_data = 0
        wrong_data = 100900

        pf = priority_field()

        try:
            pf.run_validation(wrong_data)
        except ValidationError:
            is_wrong_data_valid = False
        else:
            is_wrong_data_valid = True

        try:
            pf.run_validation(correct_data)
        except ValidationError:
            is_correct_data_valid = False
        else:
            is_correct_data_valid = True

        self.assertFalse(is_wrong_data_valid)
        self.assertTrue(is_correct_data_valid)


class TestPriorityField(TestCase):
    custom_choices = (
        (0, 'Zero'),
        (1, 'One'),
        (2, 'Two')
    )
    custom_default_parameter = 1
    default_choices = PRIORITY_CHOICES
    default_default_parameter = PRI_NONE

    def test_custom_choices(self):
        pf = priority_field(choices=self.custom_choices)
        self.assertEqual(
            tuple(pf.choices.items()),
            self.custom_choices
        )
        self.assertNotEqual(
            tuple(pf.choices.items()),
            self.default_choices
        )

    def test_custom_default_parameter(self):
        psf = priority_field(default=self.custom_default_parameter)
        self.assertEqual(
            psf.default,
            self.custom_default_parameter
        )
        self.assertNotEqual(
            psf.default,
            self.default_default_parameter
        )

    def test_default_choices(self):
        pf = priority_field()
        self.assertEqual(
            tuple(pf.choices.items()),
            self.default_choices
        )
        self.assertNotEqual(
            tuple(pf.choices.items()),
            self.custom_choices
        )

    def test_default_default_parameter(self):
        psf = priority_field()
        self.assertEqual(
            psf.default,
            self.default_default_parameter
        )
        self.assertNotEqual(
            psf.default,
            self.custom_default_parameter
        )

    def test_validation(self):

        correct_data = 0
        wrong_data = 100900

        pf = priority_field()

        try:
            pf.run_validation(wrong_data)
        except ValidationError:
            is_wrong_data_valid = False
        else:
            is_wrong_data_valid = True

        try:
            pf.run_validation(correct_data)
        except ValidationError:
            is_correct_data_valid = False
        else:
            is_correct_data_valid = True

        self.assertFalse(is_wrong_data_valid)
        self.assertTrue(is_correct_data_valid)


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
