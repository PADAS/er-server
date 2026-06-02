import json
import logging
from collections import OrderedDict
from unittest.mock import MagicMock

import pytest

from django.test import TestCase

import utils.schema_utils as schema_utils
from choices.models import Choice, DynamicChoice
from factories import DynamicChoiceFactory, SubjectFactory
from observations.models import CommonName, Subject


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestReportUtils(TestCase):
    raw_schema_1 = """{
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
}"""

    replacement_fields_schema_1 = [
        {
            "lookup": "enum",
            "field": "carcassrep_species",
            "type": "values",
            "tag": "enum___carcassrep_species___values",
        },
        {"lookup": "enum", "field": "carcassrep_species", "type": "names", "tag": "enum___carcassrep_species___names"},
        {
            "lookup": "enum",
            "field": "carcassrep_trophystatus",
            "type": "values",
            "tag": "enum___carcassrep_trophystatus___values",
        },
        {
            "lookup": "enum",
            "field": "carcassrep_trophystatus",
            "type": "names",
            "tag": "enum___carcassrep_trophystatus___names",
        },
    ]
    definition_order_schema_1 = [("carcassrep_species", 0), ("carcassrep_trophystatus", 1)]
    definition_order_dict_schema_1 = OrderedDict([("carcassrep_species", 0), ("carcassrep_trophystatus", 1)])

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
                    "enumNames": {"zebra": "Zebra"},
                },
                "carcassrep_trophystatus": {
                    "type": "string",
                    "title": "Line 7: Trophy Status",
                    "enum": [],
                    "enumNames": {},
                },
            },
        },
        "definition": ["carcassrep_species", "carcassrep_trophystatus"],
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
                    "enumNames": {"zebra": "Zebra"},
                },
                "carcassrep_trophystatus": {
                    "type": "string",
                    "title": "Line 7: Trophy Status",
                    "enum": [],
                    "enumNames": {},
                },
            },
        },
        "definition": [
            "field_1",
            {"type": "fieldset", "htmlClass": "col-lg-12", "items": ["fieldset_1_item_1", "fieldset_1_item_2"]},
            {"type": "fieldset", "htmlClass": "col-lg-12", "items": ["fieldset_2_item_1", "fieldset_2_item_2"]},
        ],
    }

    definition_order_dict_schema_2 = OrderedDict(
        [
            ("field_1", 0),
            ("fieldset_1_item_1", 1),
            ("fieldset_1_item_2", 2),
            ("fieldset_2_item_1", 3),
            ("fieldset_2_item_2", 4),
        ]
    )

    def setUp(self):
        super().setUp()

        choices = [
            {
                "model": "activity.event",
                "field": "carcassrep_species",
                "value": "zebra",
                "display": "Zebra",
            }
        ]
        Choice.objects.create(**choices[0])

    def test_get_all_replacement_fields(self):
        result = schema_utils.get_replacement_fields_in_schema(self.raw_schema_1)
        self.assertEqual(result, self.replacement_fields_schema_1)

    def test_schema_renderer(self):
        result = schema_utils.get_schema_renderer_method()(self.raw_schema_1)
        self.assertEqual(result, self.rendered_schema_1)

    def test_schema_validation(self):
        result = schema_utils.validate(MagicMock(), self.rendered_schema_1, False)
        self.assertTrue(result)

    def test_definition_key_order(self):
        result = schema_utils.definition_keys(self.rendered_schema_1.get("definition", []))
        self.assertEqual(list(result), self.definition_order_schema_1)

    def test_definition_key_order_as_dict(self):
        result = schema_utils.definition_key_order_as_dict(self.rendered_schema_1)
        self.assertEqual(result, self.definition_order_dict_schema_1)

    def test_definition_key_parsing_with_fieldsets(self):
        result = schema_utils.definition_key_order_as_dict(self.rendered_schema_2)

        self.assertEqual(result, self.definition_order_dict_schema_2)

    def test_lookup_type_query(self):
        DynamicChoice.objects.create(
            choice_name="elephants",
            model_name="observations.subject",
            criteria='[["subject_subtype", "elephant"]]',
            value_col="id",
            display_col="name",
        )

        elephant_list = []
        elephant_list.append(
            Subject.objects.create(
                **{
                    "name": "Alvin",
                    "subject_subtype_id": "elephant",
                }
            )
        )
        elephant_list.append(
            Subject.objects.create(
                **{
                    "name": "Theodore",
                    "subject_subtype_id": "elephant",
                }
            )
        )

        elephant_list = sorted(elephant_list, key=lambda subject: subject.name)
        zebra_list = []
        zebra_list.append(
            Subject.objects.create(
                **{
                    "name": "Simon",
                    "subject_subtype_id": "zebra",
                }
            )
        )

        # As values
        replacement_fields = [
            {"lookup": "query", "field": "elephants", "type": "values", "tag": "query___elephants___values"},
        ]
        values_list = schema_utils.get_dynamic_choices(
            replacement_fields[0],
        )
        self.assertListEqual([str(x.id) for x in elephant_list], json.loads(values_list))

        # As names
        replacement_fields = [
            {"lookup": "query", "field": "elephants", "type": "names", "tag": "query___elephants___names"},
        ]
        names_list = schema_utils.get_dynamic_choices(
            replacement_fields[0],
        )
        self.assertDictEqual(dict([(str(sub.id), sub.name) for sub in elephant_list]), json.loads(names_list))

        # As map
        replacement_fields = [
            {"lookup": "query", "field": "elephants", "type": "map", "tag": "query___elephants___map"},
        ]
        map_result = schema_utils.get_dynamic_choices(
            replacement_fields[0],
        )

        expected_map_result = [dict(value=str(sub.id), name=sub.name) for sub in elephant_list]
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
                    },
                },
            },
            "definition": ["reported_species", "bar"],
        }
        with self.assertRaisesRegex(schema_utils.SchemaValidationError, "reported_species.*title"):
            schema_utils.validate_rendered_schema_is_wellformed(rendered_schema_invalid_property_attributes)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDynamicChoices:

    @pytest.fixture
    def rhino_dynamic_choice(self):
        return DynamicChoiceFactory.create(
            choice_name="rhinos",
            model_name="observations.subject",
            criteria='[["common_name_id", "black_rhino"]]',
            value_col="additional__external_id",
            display_col="additional__external_name",
        )

    @pytest.fixture
    def two_rhinos(self):
        common_name_black_rhino = CommonName.objects.create(
            **{"value": "black_rhino", "display": "Black Rhino", "subject_subtype_id": "rhino"}
        )
        return [
            SubjectFactory.create(
                **{
                    "name": "Alvin",
                    "subject_subtype_id": "rhino",
                    "common_name": common_name_black_rhino,
                    "additional": dict(external_id="1234", external_name="Alvin 1234"),
                }
            ),
            Subject.objects.create(
                **{
                    "name": "Theodore",
                    "subject_subtype_id": "rhino",
                    "common_name": common_name_black_rhino,
                    "additional": dict(external_id="5678", external_name="Theodore 5678"),
                }
            ),
        ]

    @pytest.fixture
    def one_zebra(self):
        return [
            SubjectFactory.create(
                **{
                    "name": "Simon",
                    "subject_subtype_id": "zebra",
                }
            )
        ]

    def test_get_dynamic_choices_with_a_non_simple_configuration_should_return_rhino_data_and_not_zebra_data(
        self, rhino_dynamic_choice, two_rhinos, one_zebra
    ):
        rhino_list = sorted(two_rhinos, key=lambda subject: subject.name)
        replacement_fields = [
            {"lookup": "query", "field": "rhinos", "type": "names", "tag": "query___rhinos___names"},
        ]
        names_list = schema_utils.get_dynamic_choices(
            replacement_fields[0],
        )
        assert dict(
            [(sub.additional["external_id"], sub.additional["external_name"]) for sub in rhino_list]
        ) == json.loads(names_list)

    def test_get_dynamic_choices_with_a_non_simple_configuration_should_return_rhino_data_when_an_existing_event_is_used_to_refine_the_result(
        self, event_with_detail, two_rhinos, rhino_dynamic_choice
    ):
        rhino_list = sorted(two_rhinos, key=lambda subject: subject.name)
        first_rhino = rhino_list[0]
        event_with_detail.data["event_details"]["rhinos"] = first_rhino.additional["external_id"]
        replacement_fields = [
            {"lookup": "query", "field": "rhinos", "type": "names", "tag": "query___rhinos___names"},
        ]
        names_list = schema_utils.get_dynamic_choices(replacement_fields[0], event=event_with_detail.event.id)
        assert dict(
            [(sub.additional["external_id"], sub.additional["external_name"]) for sub in rhino_list]
        ) == json.loads(names_list)


class TestGetResolvedV1V2Properties:
    """Tests for get_resolved_v1v2_properties covering V1 legacy, V2 flat, and V2 conditional schemas."""

    V1_SCHEMA = {
        "schema": {
            "properties": {
                "field_a": {"type": "string", "title": "Field A"},
                "field_b": {"type": "string", "title": "Field B"},
            }
        }
    }

    V2_FLAT_SCHEMA = {
        "json": {
            "properties": {
                "top_field": {"type": "string", "title": "Top Field"},
            }
        }
    }

    V2_CONDITIONAL_SCHEMA = {
        "json": {
            "properties": {
                "status": {"type": "string", "title": "Status"},
            },
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "active"}}},
                    "then": {
                        "properties": {
                            "conditional_field": {"type": "string", "title": "Conditional Field"},
                        }
                    },
                }
            ],
        }
    }

    V2_MULTI_ALLOF_SCHEMA = {
        "json": {
            "properties": {
                "status": {"type": "string", "title": "Status"},
            },
            "allOf": [
                {
                    "then": {
                        "properties": {
                            "cond_field_1": {"type": "string", "title": "Cond Field 1"},
                        }
                    }
                },
                {
                    "then": {
                        "properties": {
                            "cond_field_2": {"type": "string", "title": "Cond Field 2"},
                        }
                    }
                },
            ],
        }
    }

    V2_ALLOF_NO_THEN_SCHEMA = {
        "json": {
            "properties": {
                "top_field": {"type": "string", "title": "Top Field"},
            },
            "allOf": [
                {"if": {"properties": {"top_field": {"const": "x"}}}},
            ],
        }
    }

    def test_v1_legacy_schema_returns_schema_properties(self):
        result = schema_utils.get_resolved_v1v2_properties(self.V1_SCHEMA)
        assert set(result.keys()) == {"field_a", "field_b"}

    def test_v2_flat_schema_returns_json_properties(self):
        result = schema_utils.get_resolved_v1v2_properties(self.V2_FLAT_SCHEMA)
        assert set(result.keys()) == {"top_field"}

    def test_v2_conditional_schema_includes_allof_then_properties(self):
        result = schema_utils.get_resolved_v1v2_properties(self.V2_CONDITIONAL_SCHEMA)
        assert "status" in result
        assert "conditional_field" in result
        assert result["conditional_field"]["title"] == "Conditional Field"

    def test_v2_conditional_schema_does_not_mutate_original(self):
        original_keys = set(self.V2_CONDITIONAL_SCHEMA["json"]["properties"].keys())
        schema_utils.get_resolved_v1v2_properties(self.V2_CONDITIONAL_SCHEMA)
        assert set(self.V2_CONDITIONAL_SCHEMA["json"]["properties"].keys()) == original_keys

    def test_v2_multiple_allof_entries_all_merged(self):
        result = schema_utils.get_resolved_v1v2_properties(self.V2_MULTI_ALLOF_SCHEMA)
        assert "status" in result
        assert "cond_field_1" in result
        assert "cond_field_2" in result

    def test_v2_allof_entry_without_then_is_skipped(self):
        result = schema_utils.get_resolved_v1v2_properties(self.V2_ALLOF_NO_THEN_SCHEMA)
        assert set(result.keys()) == {"top_field"}

    def test_empty_schema_returns_empty_dict(self):
        result = schema_utils.get_resolved_v1v2_properties({})
        assert result == {}

    def test_property_keys_order_includes_conditional_fields(self):
        result = schema_utils.property_keys_order_as_dict(self.V2_CONDITIONAL_SCHEMA)
        assert "status" in result
        assert "conditional_field" in result

    def test_detail_resolver_resolves_conditional_field(self):
        properties = schema_utils.get_resolved_v1v2_properties(self.V2_CONDITIONAL_SCHEMA)
        result = schema_utils.detail_resolver(properties, self.V2_CONDITIONAL_SCHEMA, "conditional_field", "hello")
        assert result is not None

    def test_detail_resolver_returns_none_for_unknown_field(self):
        properties = schema_utils.get_resolved_v1v2_properties(self.V2_CONDITIONAL_SCHEMA)
        result = schema_utils.detail_resolver(properties, self.V2_CONDITIONAL_SCHEMA, "nonexistent_field", "hello")
        assert result is None

    def test_get_display_value_header_for_key_resolves_conditional_field_title(self):
        result = schema_utils.get_display_value_header_for_key(self.V2_CONDITIONAL_SCHEMA, "conditional_field")
        assert result == "Conditional Field"

    @pytest.mark.parametrize(
        "schema,expected_title",
        [
            pytest.param(
                {
                    "json": {
                        "properties": {
                            "foo": {"title": "Top Foo"},
                        },
                        "allOf": [
                            {
                                "then": {
                                    "properties": {
                                        "foo": {"title": "Conditional Foo"},
                                    }
                                }
                            }
                        ],
                    }
                },
                "Conditional Foo",
                id="allOf_then_overrides_top_level",
            ),
        ],
    )
    def test_conditional_property_overrides_top_level_with_same_key(self, schema, expected_title):
        result = schema_utils.get_resolved_v1v2_properties(schema)
        assert result["foo"]["title"] == expected_title
        # Verify original schema is not mutated
        assert schema_utils.get_resolved_v1v2_properties(schema)["foo"]["title"] == expected_title
        assert schema["json"]["properties"]["foo"]["title"] == "Top Foo"


class TestExtractFromList:
    """extract_from_list must not include the full items list in each warning.

    When a list contains N non-dict values the previous implementation logged
    ``f"... from {items}"`` inside the per-item loop, allocating an O(N²)
    number of characters just for logging.  The fix logs only the item count
    so each warning is O(1).
    """

    def test_warning_message_does_not_contain_full_list(self, caplog):
        items = [f"item_{i}" for i in range(50)]
        with caplog.at_level(logging.WARNING, logger="utils.schema_utils"):
            schema_utils.extract_from_list(items)
        for record in caplog.records:
            assert str(items) not in record.getMessage(), (
                "Warning message must not dump the full items list — "
                "that causes O(N²) memory allocations for large cluster_points lists."
            )

    def test_warning_message_contains_item_count(self, caplog):
        items = ["x", "y", "z"]
        with caplog.at_level(logging.WARNING, logger="utils.schema_utils"):
            schema_utils.extract_from_list(items)
        for record in caplog.records:
            assert "3" in record.getMessage()

    def test_dict_items_produce_no_warning(self, caplog):
        items = [{"name": "foo", "value": "bar"}]
        with caplog.at_level(logging.WARNING, logger="utils.schema_utils"):
            schema_utils.extract_from_list(items)
        assert not caplog.records


class TestExtractFromDictOrString:
    def test_date_like_string_without_schema_format_is_not_converted(self):
        schema_item = {"type": "string", "title": "Version"}
        _value, display = schema_utils.extract_from_dict_or_string(schema_item, "2026-05-30-03")
        assert display == "2026-05-30-03"

    def test_date_string_with_field_html_class_is_converted(self):
        schema_item = {"type": "string", "title": "Time of Arrest", "fieldHtmlClass": "date-time-picker json-schema"}
        _value, display = schema_utils.extract_from_dict_or_string(schema_item, "2026-05-30T10:00:00.000Z")
        assert display == "2026-05-30 03:00"

    def test_extractor_converts_date_when_field_html_class_only_in_definition(self):
        schema_item = {"type": "string", "title": "Time of Arrest"}
        definition = [{"key": "arrest_time", "fieldHtmlClass": "date-time-picker json-schema"}]
        _title, _value, display = schema_utils.extractor(
            schema_item, definition, "arrest_time", "2026-05-30T10:00:00.000Z"
        )
        assert display == "2026-05-30 03:00"

    def test_extract_from_definition_fallback_walks_definition_when_no_matched_item(self):
        schema_item = {"type": "string"}
        definition = [{"key": "incident_time", "title": "Time of Incident"}]
        title, value, display = schema_utils.extract_from_definition(
            schema_item, definition, "incident_time", "raw", "raw", "raw"
        )
        assert title == "Time of Incident"
