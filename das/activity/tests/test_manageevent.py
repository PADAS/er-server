import logging
import copy

from datetime import datetime
from django.core.management import call_command
from django.test import TestCase
from drf_extra_fields.geo_fields import PointField
from rest_framework.fields import DateTimeField

from activity.management.commands.manageevent import Command
from activity.models import Event, EventType

logger = logging.getLogger(__name__)


migration_doc = [
    {
        "id": "b413783b-c162-447f-8541-e3f51cd341e8",
        "created_at": "2016-08-05 01:00:00+00:00",
        "updated_at": "2016-10-08 00:57:39.310560+00:00",
        "value": "contact",
        "previous_value": "arrest_rep",
        "display": "Contact",
        "category_value": "security",
        "category_id": "61d279a3-95fd-421f-bdb0-604ae8731761",
        "ordernum": 270,
        "schema": "{\r\n   \"schema\": \r\n   {\r\n       \"$schema\": \"http://json-schema.org/draft-04/schema#\",\r\n       \"title\": \"Sit Rep Report\",\r\n     \r\n       \"type\": \"object\",\r\n\r\n       \"properties\": \r\n       {\r\n            \"sitrepWhat\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 1: What is it?\"\r\n            },\r\n            \"sitrepCurrentActivity\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 2: Update of current activity\"\r\n            },\r\n            \"sitrepFutureActivity\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 3: Planned Future Activity\"\r\n            },\r\n            \"sitrepOther\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 4: Other\"\r\n            }\r\n       }\r\n   },\r\n \"definition\": [\r\n   \"sitrepWhat\",\r\n   \"sitrepCurrentActivity\",\r\n   \"sitrepFutureActivity\",\r\n   \"sitrepOther\"\r\n ]\r\n}",
        "is_collection": False,
        "count": 0,
        "rendered_schema": {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Animal Control Report",
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "title": "Line 3: Animal Species",
                        "enum": [],
                        "enumNames": []
                    },
                    "numberAnimals": {
                        "type": "number",
                        "title": "Line 4: # of Animals",
                        "minimum": 0
                    },
                    "reason": {
                        "type": "string",
                        "title": "Line 5: Reason"
                    },
                    "numberShotsFired": {
                        "type": "number",
                        "title": "Line 6: Number of Shots Fired",
                        "minimum": 0
                    }
                }
            },
            "definition": [
                "species",
                "numberAnimals",
                "reason",
                "numberShotsFired"
            ]
        },
        "fields": [
            {
                "property_name": "species",
                "previous_property_name": "HC:Elephant"
            },
            {
                "property_name": "numberAnimals",
                "previous_property_name": "IGNORE"
            },
            {
                "property_name": "reason",
                "previous_property_name": "reason"
            }
        ],
        "tables": [
            {
                "table_name": "Species",
                "field": "contact_species",
                "model": "activity.event"
            },
        ],
        "queries": [],
        "enums": []
    }
]


class TestManageEvent(TestCase):
    event_data = dict(
        message="Something worth recording happened",
        time=DateTimeField().to_representation(datetime.now()),
        provenance=Event.PC_SYSTEM,
        event_type='other',
        priority=Event.PRI_REFERENCE,
        location=dict(longitude='40.1353', latitude='-1.891517')
    )

    migrate_ran = False
    delete_ran = False

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')

        self.sample_event = self.create_event(self.event_data)

    def create_event(self, event_data):
        data = copy.deepcopy(event_data)
        if 'time' in event_data:
            data['event_time'] = DateTimeField().to_internal_value(
                event_data['time'])
            del data['time']
        if isinstance(event_data.get('event_type', None), str):
            data['event_type'] = EventType.objects.get_by_value(
                event_data['event_type'])

        if 'location' in data:
            data['location'] = PointField().to_internal_value(
                data['location'])
        return Event.objects.create_event(**data)

    def test_dump_data(self):
        command_under_test = Command()
        records = command_under_test.get_all_event_type_records()

        self.assertEqual(len(records), 38)

    def test_delete_unused_types(self):
        self.delete_ran = True
        command_under_test = Command()
        records = command_under_test.get_unused_event_types()

        self.assertEqual(len(records), 37)

    def test_migrate_event_type(self):
        self.migrate_ran = True
        command_under_test = Command()
        records_pre = command_under_test.get_all_event_type_records()
        command_under_test.perform_migration_on_records(migration_doc)
        records_post = command_under_test.get_all_event_type_records()
        self.assertEqual(len(records_pre), len(records_post))
