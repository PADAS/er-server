"""Tests for ChoiceProcessor - current hardcoded choice analysis helpers."""

import pytest

from activity.schemas.migration.choice_processor import (
    ChoiceProcessor,
    HardcodedChoice,
    ResolutionStrategy,
    get_field_schema_from_prop_path,
    rewrite_field_to_ref,
)
from activity.schemas.migration.service import MigrationResult
from choices.models import Choice


class TestNormalizeForMatching:
    def test_normalizes_case_and_separators(self, choice_processor):
        assert choice_processor.normalize_for_matching("UPPERCASE") == "uppercase"
        assert choice_processor.normalize_for_matching("High_Priority") == "high-priority"
        assert choice_processor.normalize_for_matching("word._-mix") == "word-mix"
        assert choice_processor.normalize_for_matching("_both_") == "both"


class TestHardcodedChoiceExtraction:
    def test_extract_hardcoded_choices_deduplicates_values(self, choice_processor):
        field_schema = {
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

        values = choice_processor.extract_hardcoded_choices(field_schema)

        assert values == [
            {"value": "open", "display": "Open"},
            {"value": "closed", "display": "closed"},
        ]

    def test_get_hardcoded_choices_collects_root_and_array_nested_paths(self, choice_processor, hardcoded_field_schema):
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

        hardcoded_choices = choice_processor.get_hardcoded_choices(v2_schema)

        assert [(choice.property_path, choice.choices) for choice in hardcoded_choices] == [
            (
                ["status"],
                [
                    {"value": "open", "display": "Open"},
                    {"value": "closed", "display": "Closed"},
                ],
            ),
            (
                ["details", "severity"],
                [
                    {"value": "low", "display": "Low"},
                    {"value": "high", "display": "High"},
                ],
            ),
        ]

    def test_extract_hardcoded_choices_ignores_ref_fields(self, choice_processor):
        assert choice_processor.extract_hardcoded_choices({"anyOf": [{"$ref": "#/definitions/some_choice"}]}) == []


class TestFindMatchingChoiceField:
    def test_returns_exact_match_for_same_values(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["priority"],
            choices=hardcoded_values(("high", "High"), ("low", "Low")),
        )

        match = choice_processor.find_matching_choice_field(
            hardcoded_choice,
            {"priority": ["high", "low"], "status": ["open", "closed"]},
        )

        assert match == ("priority", 1.0, [])

    def test_returns_partial_match_with_missing_choices_when_threshold_met(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["status"],
            choices=hardcoded_values(("open", "Open"), ("closed", "Closed"), ("pending", "Pending")),
        )

        match = choice_processor.find_matching_choice_field(
            hardcoded_choice,
            {"status": ["open", "closed"]},
        )

        assert match is not None
        field_name, score, missing_choices = match
        assert field_name == "status"
        assert score == pytest.approx(2 / 3)
        assert missing_choices == [{"value": "pending", "display": "Pending"}]

    def test_uses_normalized_overlap_for_matching(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["priority"],
            choices=hardcoded_values(("high priority", "High Priority"), ("Low_Priority", "Low Priority")),
        )

        match = choice_processor.find_matching_choice_field(
            hardcoded_choice,
            {"priority_level": ["HIGH_PRIORITY", "low-priority"]},
        )

        assert match is not None
        assert match[0] == "priority_level"

    def test_returns_none_below_threshold(self, choice_processor, hardcoded_values):
        hardcoded_choice = HardcodedChoice(
            property_path=["status"],
            choices=hardcoded_values(
                ("open", "Open"),
                ("closed", "Closed"),
                ("pending", "Pending"),
                ("archived", "Archived"),
            ),
        )

        match = choice_processor.find_matching_choice_field(
            hardcoded_choice,
            {"status": ["open"]},
        )

        assert match is None


class TestChoiceResolutionPlanning:
    def test_returns_use_existing_for_exact_existing_match(self, hardcoded_values):
        processor = ChoiceProcessor(existing_choices={"severity": ["low", "high"]})
        migration_result = MigrationResult(event_type_value="fire_rep")
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            choices=hardcoded_values(("low", "Low"), ("high", "High")),
        )

        resolutions = processor.get_possible_choice_resolutions(migration_result, hardcoded_choice)

        assert len(resolutions) == 1
        assert resolutions[0].strategy == ResolutionStrategy.USE_EXISTING
        assert resolutions[0].choice_field_name == "severity"

    def test_returns_create_and_merge_into_existing_for_partial_existing_match(self, hardcoded_values):
        processor = ChoiceProcessor(existing_choices={"severity": ["low", "high"]})
        migration_result = MigrationResult(event_type_value="fire_rep")
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            choices=hardcoded_values(("low", "Low"), ("high", "High"), ("critical", "Critical")),
        )

        resolutions = processor.get_possible_choice_resolutions(migration_result, hardcoded_choice)

        assert [resolution.strategy for resolution in resolutions] == [
            ResolutionStrategy.CREATE_NEW,
            ResolutionStrategy.MERGE_INTO_EXISTING,
        ]
        assert resolutions[1].choice_field_name == "severity"
        assert resolutions[1].missing_choices == [{"value": "critical", "display": "Critical"}]

    def test_analyze_migration_results_makes_earlier_create_available_as_use_proposed(self, hardcoded_values):
        first_result = MigrationResult(
            event_type_value="fire_rep",
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=hardcoded_values(("low", "Low"), ("high", "High")),
                )
            ],
        )
        second_result = MigrationResult(
            event_type_value="incident_rep",
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["impact"],
                    choices=hardcoded_values(("low", "Low"), ("high", "High")),
                )
            ],
        )
        processor = ChoiceProcessor()

        processor.analyze_migration_results([first_result, second_result], existing_choices={}, proposed_choices={})

        assert [option.strategy for option in first_result.hardcoded_choices[0].resolution_options] == [
            ResolutionStrategy.CREATE_NEW
        ]
        assert [option.strategy for option in second_result.hardcoded_choices[0].resolution_options] == [
            ResolutionStrategy.USE_PROPOSED
        ]
        assert second_result.hardcoded_choices[0].resolution_options[0].choice_field_name == "severity"


class TestGenerateUniqueName:
    def test_uses_field_name_when_available(self, choice_processor):
        assert choice_processor.generate_unique_name(["severity"], "fire_rep") == "severity"

    def test_uses_nested_path_candidate_before_event_type_prefix(self, choice_processor):
        choice_processor.existing_choices = {"severity": ["low"]}

        assert choice_processor.generate_unique_name(["details", "severity"], "fire_rep") == "details_severity"

    def test_uses_event_type_prefix_when_other_candidates_are_taken(self, choice_processor):
        choice_processor.existing_choices = {
            "severity": ["low"],
            "details_severity": ["low"],
        }

        assert choice_processor.generate_unique_name(["details", "severity"], "fire_rep") == "fire_rep_severity"

    def test_adds_numeric_suffix_when_all_candidates_are_taken(self, choice_processor):
        choice_processor.existing_choices = {
            "severity": ["low"],
            "details_severity": ["low"],
            "fire_rep_severity": ["low"],
            "fire_rep_details_severity": ["low"],
        }

        assert choice_processor.generate_unique_name(["details", "severity"], "fire_rep") == "severity_1"


class TestSchemaRewriteHelpers:
    def test_get_field_schema_from_prop_path_handles_nested_arrays(self):
        v2_schema = {
            "json": {
                "properties": {
                    "details": {
                        "type": "array",
                        "items": {
                            "properties": {
                                "severity": {
                                    "title": "Severity",
                                    "type": "string",
                                    "anyOf": [{"title": "Hardcoded", "oneOf": [{"const": "low"}]}],
                                }
                            }
                        },
                    }
                }
            }
        }

        field_schema = get_field_schema_from_prop_path(v2_schema, ["details", "severity"])

        assert field_schema["title"] == "Severity"

    def test_rewrite_field_to_ref_replaces_anyof_and_preserves_other_keys(self, choices_base_url):
        field_schema = {
            "title": "Severity",
            "type": "string",
            "description": "How severe",
            "anyOf": [{"title": "Hardcoded", "oneOf": [{"const": "low"}]}],
        }

        rewrite_field_to_ref(field_schema, "severity")

        assert field_schema == {
            "title": "Severity",
            "type": "string",
            "description": "How severe",
            "anyOf": [{"$ref": f"{choices_base_url}?field=severity"}],
        }


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

    def test_add_values_to_choice_field_appends_new_values_only(self, choice_processor, create_choice):
        create_choice("status", "active", "Active", 0)
        create_choice("status", "inactive", "Inactive", 1)

        added = choice_processor.add_values_to_choice_field(
            "status",
            [
                {"value": "inactive", "display": "Inactive"},
                {"value": "pending", "display": "Pending"},
                {"value": "pending", "display": "Pending Duplicate"},
                {"value": "", "display": "Empty"},
                {"value": "resolved", "display": "Resolved"},
            ],
        )

        choices = list(Choice.objects.filter(field="status").order_by("ordernum").values_list("value", "ordernum"))

        assert added == 2
        assert choices == [("active", 0), ("inactive", 1), ("pending", 2), ("resolved", 3)]
