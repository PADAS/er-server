import logging

import pytest

from django.test import TestCase

import utils.schema_utils as schema_utils

logger = logging.getLogger(__name__)


EVENT_SCHEMA_A = """
{
    "schema":
    {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Shot Rep Report",
        "type": "object",
        "properties":
        {
            "shotrepTimeOfShot":
            {
                "type": "string",
                "title": "Line 1: Time when shot was heard"
            },
            "shotrepBearing":
            {
                "type": "number",
                "title": "Line 2: Bearing to Shot",
                "minimum": 0,
                "maximum": 360
            },
            "shotrepDistance":
            {
                "type": "number",
                "title": "Line 3: Distance of Shots",
                "minimum": 0
            },
            "shotrepNumberOfShots":
            {
                "type": "number",
                "title": "Line 4: Number of Shots",
                "minimum": 0
            },
            "shotrepEstimatedCaliber":
            {
                "type": "string",
                "title": "Line 5: Estimated Caliber"
            },
            "shotrepEstimatedTarget":
            {
                "type": "string",
                "title": "Line 6: Estimated Target"
            }
        }
    },
    "definition":
    [
        {
            "key": "shotrepTimeOfShot",
            "fieldHtmlClass": "date-time-picker json-schema",
            "readonly": false
        },
        "shotrepBearing",
        "shotrepDistance",
        "shotrepNumberOfShots",
        "shotrepTypeOfShots",
        "shotrepEstimatedCaliber",
        "shotrepEstimatedTarget"
    ]
}
"""

EVENT_SCHEMA_A_CHOICE_TAGS = ("table___TypeOfShots___values", "table___TypeOfShots___names")

BAD_SCHEMA = """
{
    "schema":
    {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Shot Rep Report",
        "type": "object",
        "properties":
        {
            "shotrepTimeOfShot":
            {
                "type": "string",
                "title": "Line 1: Time when shot was heard"
            },
            "shotrepBearing":
            {
                "type": "number",
                "title": "Line 2: Bearing to Shot",
                "minimum": 0,
                "maximum": 360
            },
            "shotrepDistance":
            {
                "type": "number",
                "title": "Line 3: Distance of Shots",
                "minimum": 0
            },
            "shotrepNumberOfShots":
            {
                "type": "number",
                "title": "Line 4: Number of Shots",
                "minimum": 0
            },
            "shotrepTypeOfShots":
            {
                "type": "string",
                "title": "Line 5. Type of Shots",
                "enum": {{table__TypeOfShots__values}},
                "enumNames": {{table___TypeOfShots___names}}
            },
            "shotrepEstimatedCaliber":
            {
                "type": "string",
                "title": "Line 6: Estimated Caliber"
            },
            "shotrepEstimatedTarget":
            {
                "type": "string",
                "title": "Line 7: Estimated Target"
            }
        }
    },
    "definition":
    [
        {
            "key": "shotrepTimeOfShot",
            "fieldHtmlClass": "date-time-picker json-schema",
            "readonly": false
        },
        "shotrepBearing",
        "shotrepDistance",
        "shotrepNumberOfShots",
        "shotrepTypeOfShots",
        "shotrepEstimatedCaliber",
        "shotrepEstimatedTarget"
    ]
}
"""


@pytest.mark.usefixtures("tenant_settings")
class TestSchema(TestCase):
    def test_find_choice_table_references(self):
        fields = schema_utils.get_replacement_fields_in_schema(EVENT_SCHEMA_A)
        for field in fields:
            tag = field[schema_utils.TAG_ATTR]
            if tag not in EVENT_SCHEMA_A_CHOICE_TAGS:
                self.assertFalse(f"Tag not found: {tag}")

    def test_rendered_schema_is_json_complete(self):
        schema = schema_utils.get_rendered_schema(EVENT_SCHEMA_A)["properties"]
        logger.debug(schema)

    def test_rendered_schema_has_malformed_tag(self):
        with self.assertRaises(NameError):
            schema_utils.get_replacement_fields_in_schema(BAD_SCHEMA)
