import logging
import copy

from datetime import datetime
from django.core.management import call_command
from django.db.models import Count
from django.test import TestCase
from drf_extra_fields.geo_fields import PointField
from rest_framework.fields import DateTimeField

from activity.management.commands.manageevent import Command
from activity.models import Event, EventType, EventCategory, EventDetails
from choices.models import Color, Choice
from utils import schema_utils

logger = logging.getLogger(__name__)

migration_doc = [
    {
        "id": "74941f0d-4b89-48be-a62a-a74c78db8383",
        "created_at": "2016-08-05 01:00:00+00:00",
        "updated_at": "2016-10-08 00:57:39.310560+00:00",
        "value": "fire_rep",
        "previous_value": "arrest_rep",
        "display": "Fire",
        "category_value": "security",
        "category_id": "61d279a3-95fd-421f-bdb0-604ae8731761",
        "ordernum": 270,
        "schema": "{\r\n   \"schema\": \r\n   {\r\n       \"$schema\": \"http://json-schema.org/draft-04/schema#\",\r\n       \"title\": \"EventType Data\",\r\n     \r\n       \"type\": \"object\",\r\n\r\n       \"properties\": \r\n       {\r\n           \"post\": {\r\n               \"type\":\"string\",\r\n               \"title\": \"Line 1: Post\",\r\n               \"enum\": {{table___color___values}},\r\n               \"enumNames\": {{table___color___names}}\r\n           }\r\n       }\r\n   },\r\n \"definition\": [\r\n  \"post\"\r\n ]\r\n}",
        "is_collection": False,
        "count": 0,
        "rendered_schema": {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "EventType Data",
                "type": "object",
                "properties": {
                    "post": {
                        "type": "string",
                        "title": "Line 1: Post",
                        "enum": [
                            "753dbb6f-8b39-49c4-8d95-36d1f711f6a2",
                            "b97b6d03-f669-4a1a-9024-479fa973c711"
                        ],
                        "enumNames": {
                            "753dbb6f-8b39-49c4-8d95-36d1f711f6a2": "Black",
                            "b97b6d03-f669-4a1a-9024-479fa973c711": "White"
                        }
                    }
                }
            },
            "definition": [
                "post"
            ]
        },
        "fields": [
            "post"
        ],
        "tables": [
            {
                "table_name": "color"
            },
            {
                "table_name": "color"
            }
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
        Color.objects.bulk_create(
            [Color(id=item_id, name=item) for (item_id, item) in [
                ("753dbb6f-8b39-49c4-8d95-36d1f711f6a2", "Black"),
                ("b97b6d03-f669-4a1a-9024-479fa973c711", "White")]])
        self.schema = "{\r\n   \"schema\": \r\n   {\r\n       \"$schema\": \"http://json-schema.org/draft-04/schema#\",\r\n       \"title\": \"EventType Data\",\r\n     \r\n       \"type\": \"object\",\r\n\r\n       \"properties\": \r\n       {\r\n           \"post\": {\r\n               \"type\":\"string\",\r\n               \"title\": \"Line 1: Post\",\r\n               \"enum\": {{table___color___values}},\r\n               \"enumNames\": {{table___color___names}}\r\n           }\r\n       }\r\n   },\r\n \"definition\": [\r\n  \"post\"\r\n ]\r\n}"

        self.event_type = EventType.objects.get(id="74941f0d-4b89-48be-a62a-a74c78db8383")
        self.event_type.schema = self.schema
        self.event_type.save()

        EventDetails.objects.create(
            data={"event_details": {"name": "Ndovu", "geofence": "Lewa"}},
            event=self.sample_event)

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

        self.assertEqual(len(records), EventType.objects.count())

    def test_delete_unused_types(self):
        self.delete_ran = True
        command_under_test = Command()
        records = command_under_test.get_unused_event_types()

        def get_event_type_count(event_type):
            for row in Event.objects.filter(event_type_id=event_type.id).values(
                'event_type_id').annotate(ecount=Count('event_type_id')):
                return row['ecount']
            return 0

        unused_event_types = []

        for event_type in EventType.objects.all():
            count = get_event_type_count(event_type)
            if not count:
                unused_event_types.append(event_type)

        self.assertEqual(len(records), len(unused_event_types))

    def test_migrate_event_types_and_choices(self):
        self.migrate_ran = True
        command_under_test = Command()
        records_pre = command_under_test.get_all_event_type_records()

        # Check initial choices count before migration
        choices_count = Choice.objects.all().count()

        command_under_test.perform_migration_on_records(migration_doc)
        records_post = command_under_test.get_all_event_type_records()

        # Note one more record saved from event_data_model
        self.assertEqual(len(records_pre), len(records_post) + 1)

        # species table choices migrated to choice model
        self.assertEqual(Choice.objects.all().count(), choices_count + 2)

    def perform_migration(self):
        self.migrate_ran = True
        command_under_test = Command()
        command_under_test.perform_migration_on_records(migration_doc)

    def test_rendered_schema_display_values_after_migration(self):
        pre_schema_properties = schema_utils.get_rendered_schema(self.schema)["properties"]
        # perform migration
        self.perform_migration()
        ev_type = EventType.objects.get(id=self.event_type.id)
        post_schema_properties = schema_utils.get_rendered_schema(ev_type.schema)["properties"]

        # Check display values on rendered schema
        self.assertEqual(list(pre_schema_properties["post"]["enumNames"].values()), list(post_schema_properties["post"]["enumNames"].values()))

    def test_event_details_after_migration(self):
        # Add event details update to migration doc
        event_details_update = {
            "previous_property_name": "name",
            "property_name": "species",
            "property_value": "fatu"
        }
        migration_doc[0].get("fields").append(event_details_update)
        self.sample_event.event_type = self.event_type
        self.sample_event.save()

        # perform migration
        self.perform_migration()

        # Event details after migration
        event_details = self.sample_event.event_details.first().data["event_details"]

        self.assertEqual(event_details["species"], "fatu")
