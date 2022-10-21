from collections import OrderedDict
import json
from django.test import TestCase
import utils.schema_utils as schema_utils
from unittest.mock import MagicMock
from choices.models import Choice, DynamicChoice
from observations.models import Subject


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
                    "enum": ["zebra"],
                    "enumNames": {"zebra": "Zebra"}
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

    rendered_schema_2 = {
        "schema": {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Animal Carcass Report (carcass_rep)",
            "type": "object",
            "properties": {
                "carcassrep_species": {
                    "type": "string",
                    "title": "Line 3: Species",
                    "enum": ["zebra"],
                    "enumNames": {"zebra": "Zebra"}
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
            'field_1',
            {"type": "fieldset",
             "htmlClass": "col-lg-12",
             "items":
                 [
                     "fieldset_1_item_1",
                     "fieldset_1_item_2"
                 ]
             },
            {"type": "fieldset",
             "htmlClass": "col-lg-12",
             "items":
                 [
                     "fieldset_2_item_1",
                     "fieldset_2_item_2"
                 ]
             }
        ]
    }

    definition_order_dict_schema_2 = OrderedDict([('field_1', 0),
                                                  ('fieldset_1_item_1', 1),
                                                  ('fieldset_1_item_2', 2),
                                                  ('fieldset_2_item_1', 3),
                                                  ('fieldset_2_item_2', 4)])

    def setUp(self):
        super().setUp()

        choices = [
            {'model': 'activity.event',
             'field': 'carcassrep_species',
             'value': 'zebra',
             'display': 'Zebra',
             }
        ]
        Choice.objects.create(**choices[0])

    def test_get_all_replacement_fields(self):
        result = schema_utils.get_replacement_fields_in_schema(
            self.raw_schema_1)
        self.assertEqual(result, self.replacement_fields_schema_1)

    def test_schema_renderer(self):
        result = schema_utils.get_schema_renderer_method()(self.raw_schema_1)
        self.assertEqual(result, self.rendered_schema_1)

    def test_schema_validation(self):
        result = schema_utils.validate(
            MagicMock(), self.rendered_schema_1, False)
        self.assertTrue(result)

    def test_definition_key_order(self):
        result = schema_utils.definition_keys(
            self.rendered_schema_1.get('definition', []))
        self.assertEqual(list(result), self.definition_order_schema_1)

    def test_definition_key_order_as_dict(self):
        result = schema_utils.definition_key_order_as_dict(
            self.rendered_schema_1)
        self.assertEqual(result, self.definition_order_dict_schema_1)

    def test_definition_key_parsing_with_fieldsets(self):
        result = schema_utils.definition_key_order_as_dict(
            self.rendered_schema_2)

        print(result)
        self.assertEqual(result, self.definition_order_dict_schema_2)

    def test_lookup_type_query(self):

        # lookup = {
        #     "key": "whiteRhinos",
        #     "type": "checkboxes",
        #     "title": "White Rhino Names",
        #     "titleMap": {{query___whiteRhinos___map}}
        # },

        DynamicChoice.objects.create(**{
            'id': 'elephants',
            'model_name': 'observations.subject',
            'criteria': '[["subject_subtype", "elephant"]]',
            'value_col': 'id',
            'display_col': 'name'
        })

        elephant_list = []
        elephant_list.append(Subject.objects.create(**{
            'name': 'Alvin', 'subject_subtype_id': 'elephant',
        }))
        elephant_list.append(Subject.objects.create(**{
            'name': 'Theodore', 'subject_subtype_id': 'elephant',
        }))

        elephant_list = sorted(elephant_list, key=lambda subject: subject.name)
        zebra_list = []
        zebra_list.append(Subject.objects.create(**{
            'name': 'Simon', 'subject_subtype_id': 'zebra',
        }))

        # As values
        replacement_fields = [{'lookup': 'query', 'field': 'elephants', 'type': 'values',
                               'tag': 'query___elephants___values'}, ]
        values_list = schema_utils.get_dynamic_choices(replacement_fields[0], )
        print('Values: %s' % values_list)
        self.assertListEqual([str(x.id)
                              for x in elephant_list], json.loads(values_list))

        # As names
        replacement_fields = [{'lookup': 'query', 'field': 'elephants', 'type': 'names',
                               'tag': 'query___elephants___names'}, ]
        names_list = schema_utils.get_dynamic_choices(replacement_fields[0], )
        print('Names: %s' % names_list)
        self.assertDictEqual(dict([(str(sub.id), sub.name)
                                   for sub in elephant_list]), json.loads(names_list))

        # As map
        replacement_fields = [{'lookup': 'query', 'field': 'elephants', 'type': 'map',
                               'tag': 'query___elephants___map'}, ]
        map_result = schema_utils.get_dynamic_choices(replacement_fields[0],)
        print('Map: %s' % map_result)

        expected_map_result = [
            dict(value=str(sub.id), name=sub.name)
            for sub in elephant_list
        ]
        self.assertListEqual(expected_map_result, json.loads(map_result))

    def test_rendered_schema_requires_valid_properties(self):
        rendered_schema_invalid_property_attributes = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Animal sighting",
                "type": "object",
                "properties": {
                    "reported_species": {
                        # Expect this to have "title" property.
                        "type": "string",
                    },
                    "bar": {
                        # This is a valid, alternative construct.
                        "key": "bar"
                    }
                }
            },
            "definition": [
                "reported_species",
                "bar"
            ]
        }
        with self.assertRaisesRegex(schema_utils.SchemaValidationError,
                                    'reported_species.*title') as sve:
            schema_utils.validate_rendered_schema_is_wellformed(
                rendered_schema_invalid_property_attributes)
