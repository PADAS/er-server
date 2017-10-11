from collections import OrderedDict

from django.test import TestCase
import utils.schema_utils as schema_utils
from unittest.mock import MagicMock


class TestReportUtils(TestCase):

    raw_schema_1 = '''{
   "schema": 
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Animal Carcass Report (carcass_rep)",
       "type": "object",
       "properties": 
       {
            "carcassrep_species": {
                "type": "string",
                "title": "Line 3: Species",
               "enum": {{enum___carcassrep_species___values}},
               "enumNames": {{enum___carcassrep_species___names}}   
            },           
            "carcassrep_trophystatus": {
                "type": "string",
                "title": "Line 7: Trophy Status",
               "enum": {{enum___carcassrep_trophystatus___values}},
               "enumNames": {{enum___carcassrep_trophystatus___names}}   
            }
       }
   },
 "definition": [
   "carcassrep_species",
   "carcassrep_trophystatus"
 ]
}'''

    replacement_fields_schema_1 = [{'lookup': 'enum', 'field': 'carcassrep_species', 'type': 'values', 'tag': 'enum___carcassrep_species___values'},
                                   {'lookup': 'enum', 'field': 'carcassrep_species',
                                       'type': 'names', 'tag': 'enum___carcassrep_species___names'},
                                   {'lookup': 'enum', 'field': 'carcassrep_trophystatus',
                                       'type': 'values', 'tag': 'enum___carcassrep_trophystatus___values'},
                                   {'lookup': 'enum', 'field': 'carcassrep_trophystatus', 'type': 'names', 'tag': 'enum___carcassrep_trophystatus___names'}]
    definition_order_schema_1 = [
        ('carcassrep_species', 0), ('carcassrep_trophystatus', 1)]
    definition_order_dict_schema_1 = OrderedDict(
        [('carcassrep_species', 0), ('carcassrep_trophystatus', 1)])

    rendered_schema_1 = {
        "schema": {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Animal Carcass Report (carcass_rep)",
            "type": "object",
            "properties": {
                "carcassrep_species": {
                    "type": "string",
                    "title": "Line 3: Species",
                    "enum": [],
                    "enumNames": {}
                },
                "carcassrep_trophystatus": {
                    "type": "string",
                    "title": "Line 7: Trophy Status",
                    "enum": [],
                    "enumNames": {}
                }
            }
        },
        "definition": [
            "carcassrep_species",
            "carcassrep_trophystatus"
        ]
    }

    def setUp(self):
        super().setUp()

    def test_get_all_replacement_fields(self):
        result = schema_utils.get_replacement_fields_in_schema(
            self.raw_schema_1)
        self.assertEquals(result, self.replacement_fields_schema_1)

    def test_schema_renderer(self):
        result = schema_utils.schema_renderer()(self.raw_schema_1)
        self.assertEquals(result, self.rendered_schema_1)

    def test_schema_validation(self):
        result = schema_utils.validate(
            MagicMock(), self.rendered_schema_1, False)
        self.assertTrue(result)

    def test_definition_key_order(self):
        result = schema_utils.definition_key_order(self.rendered_schema_1)
        self.assertEquals(list(result), self.definition_order_schema_1)

    def test_definition_key_order_as_dict(self):
        result = schema_utils.definition_key_order_as_dict(
            self.rendered_schema_1)
        self.assertEquals(result, self.definition_order_dict_schema_1)
