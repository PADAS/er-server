import logging

from django.test import TestCase

import utils.schema_utils as schema_utils


logger = logging.getLogger(__name__)


EVENT_SCHEMA_A = """{\r\n   \"schema\": \r\n   {\r\n       \"$schema\": \"http://json-schema.org/draft-04/schema#\",\r\n       \"title\": \"Shot Rep Report\",\r\n     \r\n       \"type\": \"object\",\r\n\r\n       \"properties\": \r\n       {\r\n            \"shotrepTimeOfShot\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 1: Time when shot was heard\"\r\n            },\r\n            \"shotrepBearing\": {\r\n                \"type\": \"number\",\r\n                \"title\": \"Line 2: Bearing to Shot\",\r\n                \"minimum\": 0,\r\n                \"maximum\":  360\r\n            },                      \r\n            \"shotrepDistance\": {\r\n                \"type\": \"number\",\r\n                \"title\": \"Line 3: Distance of Shots\",\r\n                \"minimum\": 0\r\n            },                      \r\n            \"shotrepNumberOfShots\": {\r\n                \"type\": \"number\",\r\n                \"title\": \"Line 4: Number of Shots\",\r\n                \"minimum\": 0\r\n            },\r\n            \"shotrepTypeOfShots\": {\r\n            \t\"type\": \"string\",\r\n            \t\"title\": \"Line 5. Type of Shots\",\r\n                \"enum\": {{table___TypeOfShots___values}},\r\n                \"enumNames\": {{table___TypeOfShots___names}}\r\n            },              \r\n            \"shotrepEstimatedCaliber\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 6: Estimated Caliber\"\r\n            },\r\n            \"shotrepEstimatedTarget\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 7: Estimated Target\"\r\n            }\r\n       }\r\n   },\r\n \"definition\": [\r\n   {\r\n   \"key\": \"shotrepTimeOfShot\",\r\n   \"fieldHtmlClass\": \"date-time-picker json-schema\",\r\n   \"readonly\": false\r\n   },\r\n   \"shotrepBearing\",\r\n   \"shotrepDistance\",\r\n   \"shotrepNumberOfShots\",\r\n   \"shotrepTypeOfShots\",\r\n   \"shotrepEstimatedCaliber\",\r\n   \"shotrepEstimatedTarget\"\r\n ]\r\n}"""
EVENT_SCHEMA_A_CHOICE_TAGS = (
    'table___TypeOfShots___values', 'table___TypeOfShots___names')

BAD_SCHEMA = """{\r\n   \"schema\": \r\n   {\r\n       \"$schema\": \"http://json-schema.org/draft-04/schema#\",\r\n       \"title\": \"Shot Rep Report\",\r\n     \r\n       \"type\": \"object\",\r\n\r\n       \"properties\": \r\n       {\r\n            \"shotrepTimeOfShot\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 1: Time when shot was heard\"\r\n            },\r\n            \"shotrepBearing\": {\r\n                \"type\": \"number\",\r\n                \"title\": \"Line 2: Bearing to Shot\",\r\n                \"minimum\": 0,\r\n                \"maximum\":  360\r\n            },                      \r\n            \"shotrepDistance\": {\r\n                \"type\": \"number\",\r\n                \"title\": \"Line 3: Distance of Shots\",\r\n                \"minimum\": 0\r\n            },                      \r\n            \"shotrepNumberOfShots\": {\r\n                \"type\": \"number\",\r\n                \"title\": \"Line 4: Number of Shots\",\r\n                \"minimum\": 0\r\n            },\r\n            \"shotrepTypeOfShots\": {\r\n            \t\"type\": \"string\",\r\n            \t\"title\": \"Line 5. Type of Shots\",\r\n                \"enum\": {{table__TypeOfShots__values}},\r\n                \"enumNames\": {{table___TypeOfShots___names}}\r\n            },              \r\n            \"shotrepEstimatedCaliber\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 6: Estimated Caliber\"\r\n            },\r\n            \"shotrepEstimatedTarget\": {\r\n                \"type\": \"string\",\r\n                \"title\": \"Line 7: Estimated Target\"\r\n            }\r\n       }\r\n   },\r\n \"definition\": [\r\n   {\r\n   \"key\": \"shotrepTimeOfShot\",\r\n   \"fieldHtmlClass\": \"date-time-picker json-schema\",\r\n   \"readonly\": false\r\n   },\r\n   \"shotrepBearing\",\r\n   \"shotrepDistance\",\r\n   \"shotrepNumberOfShots\",\r\n   \"shotrepTypeOfShots\",\r\n   \"shotrepEstimatedCaliber\",\r\n   \"shotrepEstimatedTarget\"\r\n ]\r\n}"""


class TestSchema(TestCase):
    def test_find_choice_table_references(self):
        fields = schema_utils.get_replacement_fields_in_schema(EVENT_SCHEMA_A)
        for field in fields:
            tag = field[schema_utils.TAG_ATTR]
            if tag not in EVENT_SCHEMA_A_CHOICE_TAGS:
                self.assertFalse('Tag not found: {}'.format(tag))

    def test_rendered_schema_is_json_complete(self):
        schema = schema_utils.get_rendered_schema(
            EVENT_SCHEMA_A)['properties']
        logger.debug(schema)

    def test_rendered_schema_has_malformed_tag(self):
        with self.assertRaises(NameError):
            schema = schema_utils.get_replacement_fields_in_schema(BAD_SCHEMA)
