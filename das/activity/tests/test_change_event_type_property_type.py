from __future__ import annotations

import copy
import json
from io import StringIO

import pytest
from jsonschema.validators import Draft202012Validator

from django.core.management import call_command
from django.core.management.base import CommandError

from activity.management.commands.change_event_type_property_type import Command
from activity.models import EventType
from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from factories import EventTypeFactory

# ---------------------------------------------------------------------------
# Fixture schema helpers
# ---------------------------------------------------------------------------


def _v2_schema() -> dict:
    """A realistic V2 schema with one property of each relevant shape."""
    return {
        "json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "unevaluatedProperties": False,
            "required": [],
            "properties": {
                "number_of_cars": {
                    "deprecated": False,
                    "title": "Number of Cars",
                    "default": "",
                    "description": "",
                    "type": "string",
                },
                "favorite_color": {
                    "deprecated": False,
                    "title": "Favorite Color",
                    "description": "",
                    "type": "string",
                    "anyOf": [{"$ref": "/api/v2.0/schemas/choices.json?field=favorite_color"}],
                },
                "sighting_date": {
                    "deprecated": False,
                    "title": "Sighting Date",
                    "description": "",
                    "type": "string",
                    "format": "date",
                },
                "tags": {
                    "deprecated": False,
                    "title": "Tags",
                    "description": "",
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "anyOf": [{"$ref": "/api/v2.0/schemas/choices.json?field=tags"}],
                    },
                },
            },
        },
        "ui": {
            "fields": {
                "number_of_cars": {
                    "conditionalDependents": [],
                    "parent": "section-1",
                    "type": "TEXT",
                    "inputType": "SHORT_TEXT",
                    "placeholder": "",
                },
                "favorite_color": {
                    "parent": "section-1",
                    "type": "CHOICE_LIST",
                    "inputType": "DROPDOWN",
                },
                "sighting_date": {
                    "parent": "section-1",
                    "type": "DATE_TIME",
                },
                "tags": {
                    "parent": "section-1",
                    "type": "CHOICE_LIST",
                    "inputType": "LIST",
                },
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "isActive": True,
                    "label": "Details",
                    "leftColumn": [
                        {"name": "number_of_cars", "type": "field"},
                        {"name": "favorite_color", "type": "field"},
                        {"name": "sighting_date", "type": "field"},
                        {"name": "tags", "type": "field"},
                    ],
                    "rightColumn": [],
                },
            },
        },
    }


def _make_v2_event_type(**overrides) -> EventType:
    schema = overrides.pop("schema_dict", None)
    schema_text = json.dumps(schema if schema is not None else _v2_schema())
    return EventTypeFactory(version=EventType.VersionChoices.VERSION_2, schema=schema_text, **overrides)


def _make_v1_event_type(**overrides) -> EventType:
    return EventTypeFactory(version=EventType.VersionChoices.VERSION_1, **overrides)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestChangeEventTypePropertyTypeCommand:
    def test_dry_run_does_not_modify_db_or_create_revision(self) -> None:
        event_type = _make_v2_event_type(value="dry_run_type")
        original_schema = event_type.schema
        initial_revisions = event_type.revision.count()

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "dry_run_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
        )

        event_type.refresh_from_db()
        assert event_type.schema == original_schema
        assert event_type.revision.count() == initial_revisions

    def test_apply_converts_string_to_number_and_preserves_rest_of_schema(self) -> None:
        original_schema_dict = _v2_schema()
        event_type = _make_v2_event_type(value="apply_type", schema_dict=original_schema_dict)

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "apply_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        new_schema = json.loads(event_type.schema)

        new_json_property = new_schema["json"]["properties"]["number_of_cars"]
        assert new_json_property["type"] == "number"
        assert "default" not in new_json_property  # "" was dropped
        assert new_json_property["title"] == "Number of Cars"
        assert new_json_property["deprecated"] is False

        new_ui_field = new_schema["ui"]["fields"]["number_of_cars"]
        assert new_ui_field["type"] == "NUMERIC"
        assert "inputType" not in new_ui_field
        assert new_ui_field["parent"] == "section-1"
        assert new_ui_field["conditionalDependents"] == []

        untouched = copy.deepcopy(original_schema_dict)
        del untouched["json"]["properties"]["number_of_cars"]
        del untouched["ui"]["fields"]["number_of_cars"]
        new_schema_without_target = copy.deepcopy(new_schema)
        del new_schema_without_target["json"]["properties"]["number_of_cars"]
        del new_schema_without_target["ui"]["fields"]["number_of_cars"]
        assert new_schema_without_target == untouched

    def test_apply_creates_exactly_one_new_revision(self) -> None:
        event_type = _make_v2_event_type(value="revision_type")
        initial_revisions = event_type.revision.count()

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "revision_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        assert event_type.revision.count() == initial_revisions + 1

    def test_transformed_schema_validates_against_main_event_type_schema(self) -> None:
        event_type = _make_v2_event_type(value="validate_type")
        out = StringIO()

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "validate_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
            stdout=out,
        )

        event_type.refresh_from_db()
        new_schema = json.loads(event_type.schema)
        Draft202012Validator(main_event_type_schema).validate(new_schema)
        # The fixture is fully conformant, so no pre-existing-issue warning is expected.
        assert "pre-existing" not in out.getvalue()

    def test_apply_succeeds_despite_preexisting_unrelated_schema_nonconformity(self) -> None:
        # Real-world V2 schemas can carry a "choices" object on a CHOICE_LIST
        # ui field, which choice_list_field_ui_schema does not allow
        # (additionalProperties: False, no "choices" key). This must not
        # block converting an unrelated, well-formed property.
        schema_dict = _v2_schema()
        schema_dict["ui"]["fields"]["favorite_color"]["choices"] = {
            "type": "EXISTING_CHOICE_LIST",
            "existingChoiceList": ["red", "blue"],
            "myDataType": "string",
        }
        event_type = _make_v2_event_type(value="preexisting_issue_type", schema_dict=schema_dict)
        out = StringIO()

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "preexisting_issue_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
            stdout=out,
        )

        event_type.refresh_from_db()
        new_schema = json.loads(event_type.schema)
        assert new_schema["json"]["properties"]["number_of_cars"]["type"] == "number"
        assert new_schema["ui"]["fields"]["number_of_cars"]["type"] == "NUMERIC"
        # The pre-existing, unrelated nonconformity is left untouched.
        assert new_schema["ui"]["fields"]["favorite_color"]["choices"] == {
            "type": "EXISTING_CHOICE_LIST",
            "existingChoiceList": ["red", "blue"],
            "myDataType": "string",
        }

        output = out.getvalue()
        assert "pre-existing schema validation issue" in output
        assert "ui.fields.favorite_color" in output

    def test_strict_validation_rejects_a_malformed_transformed_property(self) -> None:
        malformed_json_property = {"deprecated": False, "title": "Bad", "type": "number", "unexpected_key": "oops"}
        valid_ui_field = {"parent": "section-1", "type": "NUMERIC"}

        with pytest.raises(CommandError):
            Command._validate_transformed_property(malformed_json_property, valid_ui_field)

    def test_already_converted_property_exits_cleanly_without_writing(self) -> None:
        schema_dict = _v2_schema()
        schema_dict["json"]["properties"]["number_of_cars"] = {
            "deprecated": False,
            "title": "Number of Cars",
            "type": "number",
        }
        schema_dict["ui"]["fields"]["number_of_cars"] = {
            "parent": "section-1",
            "type": "NUMERIC",
        }
        event_type = _make_v2_event_type(value="already_converted_type", schema_dict=schema_dict)
        original_schema = event_type.schema
        initial_revisions = event_type.revision.count()

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "already_converted_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        assert event_type.schema == original_schema
        assert event_type.revision.count() == initial_revisions

    def test_refuses_choice_list_property(self) -> None:
        event_type = _make_v2_event_type(value="choice_list_type")

        with pytest.raises(CommandError):
            call_command(
                "change_event_type_property_type",
                "--event-type",
                "choice_list_type",
                "--property",
                "favorite_color",
                "--to-type",
                "number",
                "--apply",
            )

        event_type.refresh_from_db()
        assert "favorite_color" in json.loads(event_type.schema)["json"]["properties"]

    def test_refuses_date_format_property(self) -> None:
        _make_v2_event_type(value="date_type")

        with pytest.raises(CommandError):
            call_command(
                "change_event_type_property_type",
                "--event-type",
                "date_type",
                "--property",
                "sighting_date",
                "--to-type",
                "number",
                "--apply",
            )

    def test_refuses_array_multi_choice_property(self) -> None:
        _make_v2_event_type(value="array_type")

        with pytest.raises(CommandError):
            call_command(
                "change_event_type_property_type",
                "--event-type",
                "array_type",
                "--property",
                "tags",
                "--to-type",
                "number",
                "--apply",
            )

    def test_refuses_missing_property_key(self) -> None:
        _make_v2_event_type(value="missing_property_type")

        with pytest.raises(CommandError):
            call_command(
                "change_event_type_property_type",
                "--event-type",
                "missing_property_type",
                "--property",
                "does_not_exist",
                "--to-type",
                "number",
                "--apply",
            )

    def test_refuses_v1_event_type(self) -> None:
        _make_v1_event_type(value="v1_type")

        with pytest.raises(CommandError):
            call_command(
                "change_event_type_property_type",
                "--event-type",
                "v1_type",
                "--property",
                "sample_attr",
                "--to-type",
                "number",
                "--apply",
            )

    def test_refuses_unknown_event_type_value(self) -> None:
        with pytest.raises(CommandError):
            call_command(
                "change_event_type_property_type",
                "--event-type",
                "does_not_exist_at_all",
                "--property",
                "number_of_cars",
                "--to-type",
                "number",
                "--apply",
            )

    def test_numeric_string_default_is_converted_to_int(self) -> None:
        schema_dict = _v2_schema()
        schema_dict["json"]["properties"]["number_of_cars"]["default"] = "3"
        event_type = _make_v2_event_type(value="numeric_default_type", schema_dict=schema_dict)

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "numeric_default_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        new_default = json.loads(event_type.schema)["json"]["properties"]["number_of_cars"]["default"]
        assert new_default == 3
        assert isinstance(new_default, int)

    def test_bool_default_is_dropped_rather_than_coerced_to_int(self) -> None:
        schema_dict = _v2_schema()
        schema_dict["json"]["properties"]["number_of_cars"]["default"] = True
        event_type = _make_v2_event_type(value="bool_default_type", schema_dict=schema_dict)

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "bool_default_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        new_json_property = json.loads(event_type.schema)["json"]["properties"]["number_of_cars"]
        assert "default" not in new_json_property

    def test_float_default_is_preserved_and_not_truncated_to_int(self) -> None:
        schema_dict = _v2_schema()
        schema_dict["json"]["properties"]["number_of_cars"]["default"] = 3.5
        event_type = _make_v2_event_type(value="float_default_type", schema_dict=schema_dict)

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "float_default_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        new_default = json.loads(event_type.schema)["json"]["properties"]["number_of_cars"]["default"]
        assert new_default == 3.5
        assert isinstance(new_default, float)

    def test_int_default_is_preserved_as_int(self) -> None:
        schema_dict = _v2_schema()
        schema_dict["json"]["properties"]["number_of_cars"]["default"] = 3
        event_type = _make_v2_event_type(value="int_default_type", schema_dict=schema_dict)

        call_command(
            "change_event_type_property_type",
            "--event-type",
            "int_default_type",
            "--property",
            "number_of_cars",
            "--to-type",
            "number",
            "--apply",
        )

        event_type.refresh_from_db()
        new_default = json.loads(event_type.schema)["json"]["properties"]["number_of_cars"]["default"]
        assert new_default == 3
        assert isinstance(new_default, int)
