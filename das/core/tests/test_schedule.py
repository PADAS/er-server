import jsonschema
from core.tests import BaseAPITest
from core.utils import OneWeekSchedule

from datetime import datetime, timedelta
import pytz
import dateutil.parser as dateparser

from django.utils import timezone

class ScheduleTestCases(BaseAPITest):

    def test_schedule_schema(self):
        valid_document_1 = {
            "schedule_type": "week",
            "periods": {
                "monday": [["00:00", "23:00"]],
                "tuesday": [["06:00", "11:00"], ["12:30", "18:30"]]
            },
            "timezone": timezone.get_current_timezone_name(),
        }

        try:
            assumed_valid = False
            jsonschema.validate(valid_document_1, OneWeekSchedule.json_schema)
            assumed_valid = True
        finally:
            self.assertTrue(assumed_valid, msg='Incorrectly assumed a schema is valid.')

        sample_date = dateparser.parse('Monday')
        self.assertTrue(sample_date in OneWeekSchedule(valid_document_1))


        invalid_document_1 = {
            "periods": {
                "monday": [["00:00", "23:00"]],
                "wednesday": [["00:01", "11:00", "12:30"]],  # <-- invalid
                "thurs": [["01:01", "12:30"]]
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid time-range tuple."):
            # jsonschema.validate(invalid_document_1, OneWeekSchedule.json_schema)
            schedule = OneWeekSchedule(invalid_document_1)

        invalid_document_2 = {
            "periods": {
                "monday": [["00:00", "23:00"]],
                "thurs": [["01:01", "12:30"]]  # <-- invalid
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for disallowed additional property."):
            jsonschema.validate(invalid_document_2, OneWeekSchedule.json_schema)

        invalid_document_3 = {
            "periods": {
                "monday": [["00:00", "23:00"]],
                "friday": [["01:01", "12:30"]],
                "somerandomkey": {'something': 1}  # <-- invalid
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for disallowed additional property."):
            jsonschema.validate(invalid_document_3, OneWeekSchedule.json_schema)

        invalid_document_4 = {
            "schedule_type": "month",
            "periods": {
                "monday": [["00:00", "23:00"]],
                "friday": [["01:01", "12:30"]]
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid schedule_type."):
            jsonschema.validate(invalid_document_4, OneWeekSchedule.json_schema)

        invalid_document_5 = {
            "schedule_type": "week",
            "periods": {
                "monday": [["00:70", "23:00"]], # <-- invalid
                "thursday": [["02:02", "23:50"]]
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid value in time-range."):

            try:
                jsonschema.validate(invalid_document_5, OneWeekSchedule.json_schema)
            except jsonschema.ValidationError as ve:
                rpath = '/'.join([''] + [str(x) for x in ve.relative_path])
                print(f'Error at {rpath}. Value {ve.instance} failed {ve.validator} match against "{ve.validator_value}"')
                print(f'Error at {rpath}. "{ve.message}"')
                raise

    def test_schedule_timezone_validation(self):
        valid_document_1 = {
            "schedule_type": "week",
            "periods": {
                "monday": [["00:00", "23:00"]],
                "tuesday": [["06:00", "11:00"], ["12:30", "18:30"]]
            },
            "timezone": 'America/Los_Angeles',
        }

        try:
            assumed_valid = False
            jsonschema.validate(valid_document_1, OneWeekSchedule.json_schema)
            assumed_valid = True
        finally:
            self.assertTrue(assumed_valid, msg='Incorrectly assumed a schema is valid.')

        sample_date = dateparser.parse('Monday')
        self.assertTrue(sample_date in OneWeekSchedule(valid_document_1))

    def test_schedule_with_invalid_timezone(self):
        valid_document_1 = {
            "schedule_type": "week",
            "periods": {
                "monday": [["00:00", "23:00"]],
                "tuesday": [["06:00", "11:00"], ["12:30", "18:30"]]
            },
            "timezone": 'Illinois/Mattoon',
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid value in timezone."):
            jsonschema.validate(valid_document_1, OneWeekSchedule.json_schema)
