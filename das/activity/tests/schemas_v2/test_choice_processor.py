"""
Tests for ChoiceProcessor - hardcoded choice analysis and matching.
"""

import pytest

from activity.schemas.migration.choice_processor import (
    ChoiceFieldResult,
    ChoiceProcessor,
)
from choices.models import Choice


class TestNormalizeForMatching:
    """Tests for the normalize_for_matching method."""

    def test_lowercase(self):
        processor = ChoiceProcessor()
        assert processor.normalize_for_matching("UPPERCASE") == "uppercase"
        assert processor.normalize_for_matching("MixedCase") == "mixedcase"

    def test_separator_normalization(self):
        processor = ChoiceProcessor()
        # All separators become dashes
        assert processor.normalize_for_matching("word_with_underscores") == "word-with-underscores"
        assert processor.normalize_for_matching("word-with-dashes") == "word-with-dashes"
        assert processor.normalize_for_matching("word.with.dots") == "word-with-dots"
        assert processor.normalize_for_matching("word with spaces") == "word-with-spaces"
        # Multiple consecutive separators become single dash
        assert processor.normalize_for_matching("word__double") == "word-double"
        assert processor.normalize_for_matching("word - spaced") == "word-spaced"
        assert processor.normalize_for_matching("word._-mix") == "word-mix"
        # Strips leading/trailing separators
        assert processor.normalize_for_matching("-leading") == "leading"
        assert processor.normalize_for_matching("trailing-") == "trailing"
        assert processor.normalize_for_matching("_both_") == "both"

    def test_combined_normalization(self):
        processor = ChoiceProcessor()
        assert processor.normalize_for_matching("High_Priority") == "high-priority"
        assert processor.normalize_for_matching("LOW PRIORITY") == "low-priority"


class TestExtractHardcodedValues:
    """Tests for extracting hardcoded choice values from V2 schemas."""

    def test_extract_from_anyof_oneof(self):
        processor = ChoiceProcessor()
        field_schema = {
            "anyOf": [
                {
                    "title": "Hardcoded",
                    "type": "string",
                    "oneOf": [
                        {"const": "value1", "title": "Display 1"},
                        {"const": "value2", "title": "Display 2"},
                    ],
                }
            ]
        }
        values = processor.extract_hardcoded_values(field_schema)
        assert len(values) == 2
        assert values[0] == {"value": "value1", "display": "Display 1"}
        assert values[1] == {"value": "value2", "display": "Display 2"}

    def test_extract_without_title_uses_const(self):
        processor = ChoiceProcessor()
        field_schema = {
            "anyOf": [
                {
                    "title": "Hardcoded",
                    "type": "string",
                    "oneOf": [
                        {"const": "simple_value"},
                    ],
                }
            ]
        }
        values = processor.extract_hardcoded_values(field_schema)
        assert len(values) == 1
        assert values[0] == {"value": "simple_value", "display": "simple_value"}

    def test_ignores_ref_fields(self):
        processor = ChoiceProcessor()
        field_schema = {
            "anyOf": [
                {"$ref": "#/definitions/some_choice"},
            ]
        }
        values = processor.extract_hardcoded_values(field_schema)
        assert values == []

    def test_empty_anyof(self):
        processor = ChoiceProcessor()
        field_schema = {"type": "string"}
        values = processor.extract_hardcoded_values(field_schema)
        assert values == []

    def test_wrong_title_not_hardcoded(self):
        processor = ChoiceProcessor()
        field_schema = {"anyOf": [{"title": "Not Hardcoded", "oneOf": [{"const": "value"}]}]}
        values = processor.extract_hardcoded_values(field_schema)
        assert values == []


class TestChoiceFieldResult:
    """Tests for the ChoiceFieldResult dataclass."""

    def test_default_values(self):
        result = ChoiceFieldResult(field_name="test_field")
        assert result.field_name == "test_field"
        assert result.status == "pending"
        assert result.existing_choice_field is None
        assert result.proposed_name is None
        assert result.values == []
        assert result.values_to_add == []
        assert result.match_score == 0.0
        assert result.warnings == []
        assert result.error is None

    def test_to_dict(self):
        result = ChoiceFieldResult(
            field_name="status",
            status="matched",
            existing_choice_field="event_status",
            match_score=0.95,
        )
        d = result.to_dict()
        assert d["field_name"] == "status"
        assert d["status"] == "matched"
        assert d["existing_choice_field"] == "event_status"
        assert d["match_score"] == 0.95


@pytest.mark.django_db
class TestFindMatchingChoiceField:
    """Tests for finding matching existing choice fields."""

    def test_exact_match(self):
        """Test matching when all values exist."""
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="priority",
            value="high",
            display="High",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="priority",
            value="low",
            display="Low",
            ordernum=1,
        )

        processor = ChoiceProcessor()
        hardcoded = [
            {"value": "high", "display": "High"},
            {"value": "low", "display": "Low"},
        ]
        match = processor.find_matching_choice_field("priority", hardcoded)

        assert match is not None
        field_name, score, missing = match
        assert field_name == "priority"
        assert score >= 0.9
        assert missing == []

    def test_partial_match_with_missing_values(self):
        """Test matching where hardcoded has extra values but still above threshold."""
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="status",
            value="open",
            display="Open",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="status",
            value="closed",
            display="Closed",
            ordernum=1,
        )

        processor = ChoiceProcessor()
        hardcoded = [
            {"value": "open", "display": "Open"},
            {"value": "closed", "display": "Closed"},
            {"value": "pending", "display": "Pending"},  # New value
        ]
        match = processor.find_matching_choice_field("status", hardcoded)

        # Jaccard: intersection=2, union=3, score=0.66 >= MATCH_THRESHOLD (2/3)
        # So it matches with the new threshold
        assert match is not None
        field_name, score, missing = match
        assert field_name == "status"
        assert len(missing) == 1
        assert missing[0]["value"] == "pending"

    def test_below_threshold_no_match(self):
        """Test that low overlap doesn't match (below 2/3 threshold)."""
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="status",
            value="open",
            display="Open",
            ordernum=0,
        )

        processor = ChoiceProcessor()
        # 1 match out of 4 = 0.25 Jaccard, well below 2/3 threshold
        hardcoded = [
            {"value": "open", "display": "Open"},
            {"value": "closed", "display": "Closed"},
            {"value": "pending", "display": "Pending"},
            {"value": "archived", "display": "Archived"},
        ]
        match = processor.find_matching_choice_field("status", hardcoded)

        # Jaccard: intersection=1, union=4, score=0.25 < MATCH_THRESHOLD (2/3)
        assert match is None

    def test_normalized_matching(self):
        """Test that matching works with different casing/separators."""
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="priority_level",
            value="HIGH_PRIORITY",
            display="High Priority",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="priority_level",
            value="low-priority",
            display="Low Priority",
            ordernum=1,
        )

        processor = ChoiceProcessor()
        hardcoded = [
            {"value": "high priority", "display": "High Priority"},  # Different format
            {"value": "Low_Priority", "display": "Low Priority"},  # Different format
        ]
        match = processor.find_matching_choice_field("priority_level", hardcoded)

        assert match is not None
        field_name, score, missing = match
        assert field_name == "priority_level"
        assert missing == []

    def test_no_match_found(self):
        """Test when no existing field matches."""
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="unrelated",
            value="value1",
            display="Value 1",
            ordernum=0,
        )

        processor = ChoiceProcessor()
        hardcoded = [
            {"value": "completely", "display": "Completely"},
            {"value": "different", "display": "Different"},
        ]
        match = processor.find_matching_choice_field("new_field", hardcoded)

        assert match is None


@pytest.mark.django_db
class TestProcessSingleField:
    """Tests for process_single_field method."""

    def test_no_match_proposes_new_field(self):
        processor = ChoiceProcessor(event_type_value="fire_rep")
        hardcoded = [
            {"value": "minor", "display": "Minor"},
            {"value": "major", "display": "Major"},
        ]
        field_schema = {"title": "Severity Level"}

        result = processor.process_single_field("severity", field_schema, hardcoded)

        assert result.status == "to_create"
        assert result.proposed_name is not None
        assert result.existing_choice_field is None

    def test_exact_match_returns_matched(self):
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="outcome",
            value="success",
            display="Success",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="outcome",
            value="failure",
            display="Failure",
            ordernum=1,
        )

        processor = ChoiceProcessor()
        hardcoded = [
            {"value": "success", "display": "Success"},
            {"value": "failure", "display": "Failure"},
        ]

        result = processor.process_single_field("outcome", {}, hardcoded)

        assert result.status == "matched"
        assert result.existing_choice_field == "outcome"
        assert result.values_to_add == []

    def test_match_with_additions(self):
        # Create 2 existing values
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="category",
            value="cat_a",
            display="Category A",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="category",
            value="cat_b",
            display="Category B",
            ordernum=1,
        )

        processor = ChoiceProcessor()
        # 2 existing + 1 new = 2/3 overlap (meets threshold)
        hardcoded = [
            {"value": "cat_a", "display": "Category A"},
            {"value": "cat_b", "display": "Category B"},
            {"value": "cat_new", "display": "New Category"},
        ]

        result = processor.process_single_field("category", {}, hardcoded)

        assert result.status == "candidate"
        assert result.existing_choice_field == "category"
        assert len(result.values_to_add) == 1


@pytest.mark.django_db
class TestCreateChoiceField:
    """Tests for create_choice_field method."""

    def test_creates_choice_objects(self):
        processor = ChoiceProcessor()
        values = [
            {"value": "red", "display": "Red Color"},
            {"value": "blue", "display": "Blue Color"},
        ]

        processor.create_choice_field("colors", values)

        choices = Choice.objects.filter(field="colors").order_by("ordernum")
        assert choices.count() == 2
        assert choices[0].value == "red"
        assert choices[0].display == "Red Color"
        assert choices[0].ordernum == 0
        assert choices[1].value == "blue"
        assert choices[1].display == "Blue Color"
        assert choices[1].ordernum == 1

    def test_skips_empty_values(self):
        processor = ChoiceProcessor()
        values = [
            {"value": "valid", "display": "Valid"},
            {"value": "", "display": "Empty"},
        ]

        processor.create_choice_field("test_field", values)

        choices = Choice.objects.filter(field="test_field")
        assert choices.count() == 1
        assert choices[0].value == "valid"


@pytest.mark.django_db
class TestAddValuesToChoiceField:
    """Tests for add_values_to_choice_field method."""

    def test_adds_new_values(self):
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="sizes",
            value="small",
            display="Small",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="sizes",
            value="medium",
            display="Medium",
            ordernum=1,
        )

        processor = ChoiceProcessor()
        new_values = [
            {"value": "large", "display": "Large"},
            {"value": "xlarge", "display": "Extra Large"},
        ]

        added = processor.add_values_to_choice_field("sizes", new_values)

        assert added == 2
        choices = Choice.objects.filter(field="sizes").order_by("ordernum")
        assert choices.count() == 4
        assert choices[2].value == "large"
        assert choices[2].ordernum == 2
        assert choices[3].value == "xlarge"
        assert choices[3].ordernum == 3

    def test_skips_existing_values(self):
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="status",
            value="active",
            display="Active",
            ordernum=0,
        )

        processor = ChoiceProcessor()
        values = [
            {"value": "active", "display": "Active"},  # Already exists
            {"value": "inactive", "display": "Inactive"},  # New
        ]

        added = processor.add_values_to_choice_field("status", values)

        assert added == 1
        assert Choice.objects.filter(field="status").count() == 2


@pytest.mark.django_db
class TestProcessHardcodedChoices:
    """Tests for the main process_hardcoded_choices method."""

    def test_processes_multiple_fields(self):
        processor = ChoiceProcessor(event_type_value="test_event")
        v2_schema = {
            "json": {
                "properties": {
                    "priority": {
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "oneOf": [
                                    {"const": "high", "title": "High"},
                                    {"const": "low", "title": "Low"},
                                ],
                            }
                        ]
                    },
                    "status": {
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "oneOf": [
                                    {"const": "open", "title": "Open"},
                                    {"const": "closed", "title": "Closed"},
                                ],
                            }
                        ]
                    },
                    "description": {
                        "type": "string",  # Not a choice field
                    },
                }
            }
        }

        result_schema, metadata = processor.process_hardcoded_choices(v2_schema)

        assert len(metadata["fields"]) == 2
        assert metadata["summary"]["to_create"] == 2
        field_names = {f["field_name"] for f in metadata["fields"]}
        assert field_names == {"priority", "status"}

    def test_ignores_non_choice_fields(self):
        processor = ChoiceProcessor()
        v2_schema = {
            "json": {
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                }
            }
        }

        _, metadata = processor.process_hardcoded_choices(v2_schema)

        assert metadata["fields"] == []
        assert metadata["summary"]["to_create"] == 0


@pytest.mark.django_db
class TestGenerateUniqueName:
    """Tests for generate_unique_name method."""

    def test_uses_field_name_when_available(self):
        processor = ChoiceProcessor()
        name = processor.generate_unique_name("my_field", {})
        assert name == "my_field"

    def test_uses_title_when_field_name_taken(self):
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="my_field",
            value="val",
            display="Val",
            ordernum=0,
        )

        processor = ChoiceProcessor()
        name = processor.generate_unique_name("my_field", {"title": "Better Name"})
        assert name == "better_name"

    def test_uses_event_type_prefix_when_others_taken(self):
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="status",
            value="val",
            display="Val",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="current_status",
            value="val",
            display="Val",
            ordernum=0,
        )

        processor = ChoiceProcessor(event_type_value="fire_rep")
        name = processor.generate_unique_name("status", {"title": "Current Status"})
        assert name == "fire_rep_status"

    def test_adds_numeric_suffix_when_all_taken(self):
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="status",
            value="val",
            display="Val",
            ordernum=0,
        )
        Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field="fire_status",
            value="val",
            display="Val",
            ordernum=0,
        )

        processor = ChoiceProcessor(event_type_value="fire")
        name = processor.generate_unique_name("status", {"title": "Fire Status"})
        assert name == "status_1"
