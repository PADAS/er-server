"""Tests for the legacy V2 event-type schema normalization layer.

See ``activity/schemas/normalization.py``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rest_framework.serializers import ValidationError

from activity.models import EventType
from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.schemas.normalization import normalize_v2_schema
from activity.serializers.event_types_v2 import EventTypeV2Serializer
from activity.serializers.fields.json_schema import JSONSchemaField
from activity.tests.helpers.schema_test_utils import (
    minimal_json_schema,
    minimal_ui_schema,
)


def _load_fixture(name: str) -> dict:
    fixture_path = Path(__file__).parent.parent / "fixtures" / f"{name}.json"
    with open(fixture_path) as f:
        return json.load(f)


class TestNonV2InputIsPassthrough:
    """Documents not shaped like a V2 schema (missing 'json' or 'ui') are returned untouched."""

    @pytest.mark.parametrize(
        "document",
        [{}, {"json": {}}, {"ui": {}}, {"schema": {"type": "object"}, "definition": []}, None, "not a dict"],
    )
    def test_returns_input_unchanged(self, document):
        assert normalize_v2_schema(document) == document


class TestAdditionalPropertiesToUnevaluatedPropertiesTransform:
    """Transform 1 (Event-Type-Schema-Migration-Tool PR #11): additionalProperties -> unevaluatedProperties."""

    def test_replaces_root_additional_properties_false_with_unevaluated_properties(self):
        document = {
            "json": {**copy.deepcopy(minimal_json_schema)},
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        del document["json"]["unevaluatedProperties"]
        document["json"]["additionalProperties"] = False

        result = normalize_v2_schema(document)

        assert "additionalProperties" not in result["json"]
        assert result["json"]["unevaluatedProperties"] is False

    def test_replaces_additional_properties_in_nested_collection_items(self):
        """The walk covers the whole 'json' subtree, including nested collection 'items'."""
        document = {
            "json": {
                **copy.deepcopy(minimal_json_schema),
                "properties": {
                    "arrests": {
                        "deprecated": False,
                        "title": "Arrests",
                        "type": "array",
                        "unevaluatedItems": False,
                        "items": {
                            "type": "object",
                            "required": [],
                            "additionalProperties": False,
                            "properties": {"name": {"deprecated": False, "title": "Name", "type": "string"}},
                        },
                    }
                },
            },
            "ui": copy.deepcopy(minimal_ui_schema),
        }

        result = normalize_v2_schema(document)

        items = result["json"]["properties"]["arrests"]["items"]
        assert "additionalProperties" not in items
        assert items["unevaluatedProperties"] is False

    def test_leaves_dict_valued_additional_properties_alone(self):
        """additionalProperties: {...} is schema composition, not the legacy boolean-false shape."""
        document = {
            "json": {**copy.deepcopy(minimal_json_schema), "additionalProperties": {"type": "string"}},
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        del document["json"]["unevaluatedProperties"]

        result = normalize_v2_schema(document)

        assert result["json"]["additionalProperties"] == {"type": "string"}
        assert "unevaluatedProperties" not in result["json"]


class TestAddUnevaluatedItemsToCollectionsTransform:
    """Transform 2: add unevaluatedItems: false to COLLECTION field arrays that lack it."""

    def _document_with_collection(self, ui_type="COLLECTION"):
        return {
            "json": {
                **copy.deepcopy(minimal_json_schema),
                "properties": {
                    "a_collection": {
                        "deprecated": False,
                        "title": "A collection",
                        "type": "array",
                        "items": {"type": "object", "required": [], "unevaluatedProperties": False, "properties": {}},
                    }
                },
            },
            "ui": {
                **copy.deepcopy(minimal_ui_schema),
                "fields": {
                    "a_collection": {
                        "columns": 1,
                        "itemName": "Item",
                        "leftColumn": [],
                        "rightColumn": [],
                        "parent": "section-1",
                        "type": ui_type,
                    }
                },
            },
        }

    def test_adds_unevaluated_items_when_missing_on_a_collection_field(self):
        result = normalize_v2_schema(self._document_with_collection())

        assert result["json"]["properties"]["a_collection"]["unevaluatedItems"] is False

    def test_does_not_add_unevaluated_items_to_an_attachment_array(self):
        """ATTACHMENT fields are also type: array in json but must never get unevaluatedItems."""
        document = self._document_with_collection(ui_type="ATTACHMENT")

        result = normalize_v2_schema(document)

        assert "unevaluatedItems" not in result["json"]["properties"]["a_collection"]

    def test_adds_unevaluated_items_to_a_collection_nested_inside_another_collection(self):
        """Dotted ui.fields id (outer.inner) routes to the nested json array node."""
        document = {
            "json": {
                **copy.deepcopy(minimal_json_schema),
                "properties": {
                    "outer": {
                        "deprecated": False,
                        "title": "Outer",
                        "type": "array",
                        "unevaluatedItems": False,
                        "items": {
                            "type": "object",
                            "required": [],
                            "unevaluatedProperties": False,
                            "properties": {
                                "inner": {
                                    "deprecated": False,
                                    "title": "Inner",
                                    "type": "array",
                                    # Missing unevaluatedItems -- the legacy gap.
                                    "items": {
                                        "type": "object",
                                        "required": [],
                                        "unevaluatedProperties": False,
                                        "properties": {},
                                    },
                                }
                            },
                        },
                    }
                },
            },
            "ui": {
                **copy.deepcopy(minimal_ui_schema),
                "fields": {
                    "outer": {
                        "columns": 1,
                        "itemName": "Outer item",
                        "leftColumn": ["outer.inner"],
                        "rightColumn": [],
                        "parent": "section-1",
                        "type": "COLLECTION",
                    },
                    "outer.inner": {
                        "columns": 1,
                        "itemName": "Inner item",
                        "leftColumn": [],
                        "rightColumn": [],
                        "parent": "outer",
                        "type": "COLLECTION",
                    },
                },
            },
        }

        result = normalize_v2_schema(document)

        inner = result["json"]["properties"]["outer"]["items"]["properties"]["inner"]
        assert inner["unevaluatedItems"] is False


class TestPopLegacyUiChoicesTransform:
    """Transform 3 (Event-Type-Schema-Migration-Tool PR #13): drop legacy ui.fields[*].choices."""

    def test_pops_choices_from_a_ui_field(self):
        document = {
            "json": copy.deepcopy(minimal_json_schema),
            "ui": {
                **copy.deepcopy(minimal_ui_schema),
                "fields": {
                    "testChoice": {
                        "inputType": "DROPDOWN",
                        "parent": "section-1",
                        "type": "CHOICE_LIST",
                        "choices": {"type": "EXISTING_CHOICE_LIST", "existingChoiceList": ["field_a"]},
                    }
                },
            },
        }

        result = normalize_v2_schema(document)

        assert "choices" not in result["ui"]["fields"]["testChoice"]

    def test_pops_legacy_choices_from_nested_collection_ui_field(self):
        document = {
            "json": copy.deepcopy(minimal_json_schema),
            "ui": {
                **copy.deepcopy(minimal_ui_schema),
                "fields": {
                    "arrests": {
                        "columns": 1,
                        "itemName": "Arrestee",
                        "leftColumn": ["arrests.species"],
                        "rightColumn": [],
                        "parent": "section-1",
                        "type": "COLLECTION",
                    },
                    "arrests.species": {
                        "inputType": "DROPDOWN",
                        "parent": "arrests",
                        "type": "CHOICE_LIST",
                        "choices": {"type": "EXISTING_CHOICE_LIST", "existingChoiceList": ["species"]},
                    },
                },
            },
        }

        result = normalize_v2_schema(document)

        assert "choices" not in result["ui"]["fields"]["arrests.species"]

    def test_does_not_touch_x_dynamic_choice_marker(self):
        """The dynamic-choice marker belongs to a different flow (ERA-13508) and must be left alone."""
        document = {
            "json": copy.deepcopy(minimal_json_schema),
            "ui": {
                **copy.deepcopy(minimal_ui_schema),
                "fields": {
                    "testChoice": {
                        "inputType": "DROPDOWN",
                        "parent": "section-1",
                        "type": "CHOICE_LIST",
                        "choices": {"type": "EXISTING_CHOICE_LIST", "existingChoiceList": ["field_a"]},
                        "x-dynamic-choice": {"choiceName": "blackRhinos", "multiple": False},
                    }
                },
            },
        }

        result = normalize_v2_schema(document)

        assert "choices" not in result["ui"]["fields"]["testChoice"]
        assert result["ui"]["fields"]["testChoice"]["x-dynamic-choice"] == {
            "choiceName": "blackRhinos",
            "multiple": False,
        }


class TestInputIsNeverMutated:
    def test_original_document_is_unchanged_after_normalizing_a_legacy_document(self):
        document = _load_fixture("legacy_v2_nested_collection_combined_schema")
        before = copy.deepcopy(document)

        result = normalize_v2_schema(document)

        assert document == before
        assert result != document


class TestIdempotence:
    @pytest.mark.parametrize("fixture_name", ["valid_event_type_v2_schema", "valid_nested_collection_schema"])
    def test_already_current_documents_are_a_no_op(self, fixture_name):
        document = _load_fixture(fixture_name)

        assert normalize_v2_schema(document) == document


class TestFieldLevelNormalization:
    """JSONSchemaField.to_internal_value normalizes before validating, per activity/serializers/fields/json_schema.py."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "legacy_v2_additional_properties_schema",
            "legacy_v2_ui_choices_schema",
            "legacy_v2_nested_collection_combined_schema",
        ],
    )
    def test_legacy_fixture_validates_and_returns_the_normalized_document(self, fixture_name):
        document = _load_fixture(fixture_name)
        field = JSONSchemaField(meta_schema=main_event_type_schema)

        result = field.to_internal_value(document)

        assert "unevaluatedProperties" in result["json"]
        assert "additionalProperties" not in result["json"]
        for ui_field in result["ui"]["fields"].values():
            assert "choices" not in ui_field
        # Normalizing twice equals normalizing once.
        assert normalize_v2_schema(result) == result

    def test_document_invalid_even_after_normalization_still_raises_validation_error(self):
        """A legacy shape sits alongside an unrelated, still-broken constraint."""
        document = {
            "json": {**copy.deepcopy(minimal_json_schema), "additionalProperties": False},
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        del document["json"]["unevaluatedProperties"]
        del document["json"]["type"]  # Missing required key -- normalization can't fix this.

        field = JSONSchemaField(meta_schema=main_event_type_schema)

        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(document)

        assert "'type' is a required property" in str(exc_info.value)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestSerializerPersistsNormalizedDocument:
    """A full legacy schema through EventTypeV2Serializer persists the normalized (current-spec) shape."""

    def test_saving_a_legacy_schema_persists_the_normalized_document(self, cat1_cat2_categories):
        cat1, _ = cat1_cat2_categories
        legacy_document = _load_fixture("legacy_v2_nested_collection_combined_schema")

        serializer = EventTypeV2Serializer(
            data={
                "value": "legacy-schema-event-type",
                "display": "Legacy Schema Event Type",
                "category": cat1.value,
                "schema": legacy_document,
            }
        )
        assert serializer.is_valid(), serializer.errors
        event_type = serializer.save()

        persisted_schema = json.loads(EventType.objects.get(pk=event_type.pk).schema)
        assert "unevaluatedProperties" in persisted_schema["json"]
        assert "additionalProperties" not in persisted_schema["json"]
        for ui_field in persisted_schema["ui"]["fields"].values():
            assert "choices" not in ui_field
