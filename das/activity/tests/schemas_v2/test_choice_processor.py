"""Tests for ChoiceProcessor - current hardcoded choice analysis helpers."""

import pytest

from activity.schemas.migration.choice_processor import (
    ChoiceProcessor,
    HardcodedChoice,
    ResolutionStrategy,
)
from activity.schemas.migration.logger import LogContext, MigrationLogger
from activity.schemas.migration.service import MigrationResult
from choices.models import Choice

_test_context = LogContext(migration_request_id="MR-test", tenant_name="test", dry_run=True)
_test_logger = MigrationLogger(context=_test_context)


class TestHardcodedChoiceExtraction:
    """All tests exercise the public get_hardcoded_choices entry point."""

    def test_deduplicates_values_within_a_field(self, choice_processor):
        v2_schema = {
            "json": {
                "properties": {
                    "status": {
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "open", "title": "Open"},
                                    {"const": "open", "title": "Open Duplicate"},
                                    {"const": "closed"},
                                ],
                            }
                        ]
                    }
                }
            }
        }

        results = choice_processor.get_hardcoded_choices(v2_schema)

        assert len(results) == 1
        assert results[0].property_path == ["status"]
        assert results[0].choices == [
            {"value": "open", "display": "Open"},
            {"value": "closed", "display": "closed"},
        ]

    def test_collects_root_and_array_nested_paths(self, choice_processor, hardcoded_field_schema):
        v2_schema = {
            "json": {
                "properties": {
                    "status": hardcoded_field_schema(("open", "Open"), ("closed", "Closed")),
                    "details": {
                        "type": "array",
                        "items": {"properties": {"severity": hardcoded_field_schema(("low", "Low"), ("high", "High"))}},
                    },
                    "description": {"type": "string"},
                }
            }
        }

        results = choice_processor.get_hardcoded_choices(v2_schema)

        assert [(r.property_path, r.choices) for r in results] == [
            (["status"], [{"value": "open", "display": "Open"}, {"value": "closed", "display": "Closed"}]),
            (["details", "severity"], [{"value": "low", "display": "Low"}, {"value": "high", "display": "High"}]),
        ]

    def test_ignores_fields_with_ref(self, choice_processor):
        v2_schema = {
            "json": {
                "properties": {
                    "category": {"anyOf": [{"$ref": "#/definitions/some_choice"}]},
                }
            }
        }

        assert choice_processor.get_hardcoded_choices(v2_schema) == []

    def test_ignores_plain_fields_without_choices(self, choice_processor):
        v2_schema = {
            "json": {
                "properties": {
                    "description": {"type": "string"},
                    "count": {"type": "number"},
                }
            }
        }

        assert choice_processor.get_hardcoded_choices(v2_schema) == []

    def test_returns_empty_for_schema_with_no_properties(self, choice_processor):
        assert choice_processor.get_hardcoded_choices({"json": {}}) == []
        assert choice_processor.get_hardcoded_choices({}) == []

    def test_skips_empty_array_collections(self, choice_processor):
        v2_schema = {
            "json": {
                "properties": {
                    "items_list": {"type": "array", "items": {}},
                }
            }
        }

        assert choice_processor.get_hardcoded_choices(v2_schema) == []

    def test_mixed_ref_and_hardcoded_fields(self, choice_processor, hardcoded_field_schema):
        v2_schema = {
            "json": {
                "properties": {
                    "ref_field": {"anyOf": [{"$ref": "/api/v1.0/choices?field=status"}]},
                    "hardcoded_field": hardcoded_field_schema(("a", "A"), ("b", "B")),
                    "plain_field": {"type": "string"},
                }
            }
        }

        results = choice_processor.get_hardcoded_choices(v2_schema)

        assert len(results) == 1
        assert results[0].property_path == ["hardcoded_field"]
        assert results[0].choices == [{"value": "a", "display": "A"}, {"value": "b", "display": "B"}]


class TestFindExactMatchingChoiceField:
    def test_returns_field_name_for_exact_value_match(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["priority"],
            choices=hardcoded_values(("high", "High"), ("low", "Low")),
        )

        match = choice_processor.find_exact_matching_choice_field(
            hardcoded_choice,
            {"priority": ["high", "low"], "status": ["open", "closed"]},
        )

        assert match == "priority"

    def test_returns_none_when_values_partially_overlap(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["status"],
            choices=hardcoded_values(("open", "Open"), ("closed", "Closed"), ("pending", "Pending")),
        )

        match = choice_processor.find_exact_matching_choice_field(
            hardcoded_choice,
            {"status": ["open", "closed"]},
        )

        assert match is None

    def test_returns_none_when_no_fields_match(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["status"],
            choices=hardcoded_values(("open", "Open"), ("closed", "Closed")),
        )

        match = choice_processor.find_exact_matching_choice_field(
            hardcoded_choice,
            {"priority": ["high", "low"]},
        )

        assert match is None


class TestChoiceResolutionPlanning:
    def test_returns_use_existing_for_exact_existing_match(self, hardcoded_values):
        processor = ChoiceProcessor()
        processor.existing_choices = {"severity": ["low", "high"]}
        migration_result = MigrationResult(event_type_value="fire_rep", log=_test_logger.for_event_type("fire_rep"))
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            choices=hardcoded_values(("low", "Low"), ("high", "High")),
        )

        resolutions = processor.get_resolution_options(migration_result, hardcoded_choice)

        assert [r.strategy for r in resolutions] == [
            ResolutionStrategy.USE_EXISTING,
            ResolutionStrategy.CREATE_NEW,
        ]
        assert resolutions[0].choice_field_name == "severity"

    def test_returns_only_create_new_for_partial_existing_match(self, hardcoded_values):
        processor = ChoiceProcessor()
        processor.existing_choices = {"severity": ["low", "high"]}
        migration_result = MigrationResult(event_type_value="fire_rep", log=_test_logger.for_event_type("fire_rep"))
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            choices=hardcoded_values(("low", "Low"), ("high", "High"), ("critical", "Critical")),
        )

        resolutions = processor.get_resolution_options(migration_result, hardcoded_choice)

        assert [resolution.strategy for resolution in resolutions] == [
            ResolutionStrategy.CREATE_NEW,
        ]

    def test_populate_resolution_options_makes_earlier_create_available_as_use_proposed(self, hardcoded_values):
        first_result = MigrationResult(
            event_type_value="fire_rep",
            log=_test_logger.for_event_type("fire_rep"),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=hardcoded_values(("low", "Low"), ("high", "High")),
                )
            ],
        )
        second_result = MigrationResult(
            event_type_value="incident_rep",
            log=_test_logger.for_event_type("incident_rep"),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["impact"],
                    choices=hardcoded_values(("low", "Low"), ("high", "High")),
                )
            ],
        )
        processor = ChoiceProcessor()

        processor.populate_resolution_options([first_result, second_result], existing_choices={}, proposed_choices={})

        assert [option.strategy for option in first_result.hardcoded_choices[0].resolution_options] == [
            ResolutionStrategy.CREATE_NEW
        ]
        assert [option.strategy for option in second_result.hardcoded_choices[0].resolution_options] == [
            ResolutionStrategy.USE_PROPOSED,
            ResolutionStrategy.CREATE_NEW,
        ]
        assert second_result.hardcoded_choices[0].resolution_options[0].choice_field_name == "severity"


class TestGenerateUniqueName:
    def test_uses_field_name_when_available(self, choice_processor):
        assert choice_processor.generate_unique_choice_field_name(["severity"], "fire_rep") == "severity"

    def test_uses_nested_path_candidate_before_event_type_prefix(self, choice_processor):
        choice_processor.existing_choices = {"severity": ["low"]}

        assert (
            choice_processor.generate_unique_choice_field_name(["details", "severity"], "fire_rep")
            == "details_severity"
        )

    def test_uses_event_type_prefix_when_other_candidates_are_taken(self, choice_processor):
        choice_processor.existing_choices = {
            "severity": ["low"],
            "details_severity": ["low"],
        }

        assert (
            choice_processor.generate_unique_choice_field_name(["details", "severity"], "fire_rep")
            == "fire_rep_details_severity"
        )

    def test_truncates_and_abbreviates_very_long_names(self, choice_processor):
        """Tests that long names are correctly abbreviated and truncated to fit within 40 chars."""
        choice_processor.existing_choices = {}

        # This combination would normally be:
        # "an_extremely_long_event_type_name_with_many_words_another_long_folder_path_and_a_very_long_field_name"
        # which is > 100 characters.

        result = choice_processor.generate_unique_choice_field_name(
            ["another_long_folder_path", "and_a_very_long_field_name"],
            "an_extremely_long_event_type_name_with_many_words",
        )

        assert len(result) <= 40

        # We need to simulate taking ALL fallback options to force the _1 suffix
        # The generator tries:
        # 1. field_name directly (and_a_very_long_field_name)
        # 2. path -> anthr_lng_fldr_pth_and_a_vry_lng_fld_nm
        # 3. event_type + field -> an_extrmly_lng_evnt_typ_nm_wth_mny_wrds
        # 4. event_type + path  -> same abbreviation as #3 (deduped)

        # Fill the dictionary with all possible fallback names
        choice_processor.existing_choices = {
            "and_a_very_long_field_name": ["x"],
            "anthr_lng_fldr_pth_and_a_vry_lng_fld_nm": ["y"],
            "an_extrmly_lng_evnt_typ_nm_wth_mny_wrds": ["z"],
        }

        result2 = choice_processor.generate_unique_choice_field_name(
            ["another_long_folder_path", "and_a_very_long_field_name"],
            "an_extremely_long_event_type_name_with_many_words",
        )

        assert len(result2) <= 40
        assert result2.endswith("_1")

    def test_adds_numeric_suffix_when_all_candidates_are_taken(self, choice_processor):
        choice_processor.existing_choices = {
            "severity": ["low"],
            "details_severity": ["low"],
            "fire_rep_severity": ["low"],
            "fire_rep_details_severity": ["low"],
        }

        assert choice_processor.generate_unique_choice_field_name(["details", "severity"], "fire_rep") == "severity_1"


@pytest.mark.django_db
class TestChoicePersistenceHelpers:
    def test_create_choice_field_preserves_order_and_skips_duplicates(self, choice_processor):
        choice_processor.create_choice_field(
            "colors",
            [
                {"value": "red", "display": "Red"},
                {"value": "red", "display": "Red Duplicate"},
                {"value": "", "display": "Empty"},
                {"value": "blue", "display": "Blue"},
            ],
        )

        choices = list(Choice.objects.filter(field="colors").order_by("ordernum").values_list("value", "ordernum"))

        assert choices == [("red", 0), ("blue", 1)]
