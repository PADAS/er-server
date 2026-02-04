"""
Tests for ChoiceProcessor - hardcoded choice analysis and matching.
"""

import pytest

from activity.schemas.migration.choice_processor import ChoiceFieldResult
from choices.models import Choice


class TestNormalizeForMatching:
    """Tests for the normalize_for_matching method."""

    def test_lowercase(self, choice_processor):
        assert choice_processor.normalize_for_matching("UPPERCASE") == "uppercase"
        assert choice_processor.normalize_for_matching("MixedCase") == "mixedcase"

    def test_separator_normalization(self, choice_processor):
        # All separators become dashes
        assert choice_processor.normalize_for_matching("word_with_underscores") == "word-with-underscores"
        assert choice_processor.normalize_for_matching("word-with-dashes") == "word-with-dashes"
        assert choice_processor.normalize_for_matching("word.with.dots") == "word-with-dots"
        assert choice_processor.normalize_for_matching("word with spaces") == "word-with-spaces"
        # Multiple consecutive separators become single dash
        assert choice_processor.normalize_for_matching("word__double") == "word-double"
        assert choice_processor.normalize_for_matching("word - spaced") == "word-spaced"
        assert choice_processor.normalize_for_matching("word._-mix") == "word-mix"
        # Strips leading/trailing separators
        assert choice_processor.normalize_for_matching("-leading") == "leading"
        assert choice_processor.normalize_for_matching("trailing-") == "trailing"
        assert choice_processor.normalize_for_matching("_both_") == "both"

    def test_combined_normalization(self, choice_processor):
        assert choice_processor.normalize_for_matching("High_Priority") == "high-priority"
        assert choice_processor.normalize_for_matching("LOW PRIORITY") == "low-priority"


class TestExtractHardcodedValues:
    """Tests for extracting hardcoded choice values from V2 schemas."""

    def test_extract_from_anyof_oneof(self, choice_processor, hardcoded_field_schema):
        field_schema = hardcoded_field_schema(("value1", "Display 1"), ("value2", "Display 2"))
        values = choice_processor.extract_hardcoded_values(field_schema)

        assert len(values) == 2
        assert values[0] == {"value": "value1", "display": "Display 1"}
        assert values[1] == {"value": "value2", "display": "Display 2"}

    def test_extract_without_title_uses_const(self, choice_processor):
        field_schema = {"anyOf": [{"title": "Hardcoded", "type": "string", "oneOf": [{"const": "simple_value"}]}]}
        values = choice_processor.extract_hardcoded_values(field_schema)

        assert len(values) == 1
        assert values[0] == {"value": "simple_value", "display": "simple_value"}

    def test_ignores_ref_fields(self, choice_processor):
        field_schema = {"anyOf": [{"$ref": "#/definitions/some_choice"}]}
        values = choice_processor.extract_hardcoded_values(field_schema)
        assert values == []

    def test_empty_anyof(self, choice_processor):
        field_schema = {"type": "string"}
        values = choice_processor.extract_hardcoded_values(field_schema)
        assert values == []

    def test_wrong_title_not_hardcoded(self, choice_processor):
        field_schema = {"anyOf": [{"title": "Not Hardcoded", "oneOf": [{"const": "value"}]}]}
        values = choice_processor.extract_hardcoded_values(field_schema)
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

    def test_exact_match(self, choice_processor, create_choice_field, hardcoded_values):
        """Test matching when all values exist."""
        create_choice_field("priority", [("high", "High"), ("low", "Low")])
        hardcoded = hardcoded_values(("high", "High"), ("low", "Low"))

        match = choice_processor.find_matching_choice_field("priority", hardcoded)

        assert match is not None
        field_name, score, missing = match
        assert field_name == "priority"
        assert score >= 0.9
        assert missing == []

    def test_partial_match_with_missing_values(self, choice_processor, create_choice_field, hardcoded_values):
        """Test matching where hardcoded has extra values but still above threshold."""
        create_choice_field("status", [("open", "Open"), ("closed", "Closed")])
        hardcoded = hardcoded_values(("open", "Open"), ("closed", "Closed"), ("pending", "Pending"))

        match = choice_processor.find_matching_choice_field("status", hardcoded)

        # Jaccard: intersection=2, union=3, score=0.66 >= MATCH_THRESHOLD (2/3)
        assert match is not None
        field_name, score, missing = match
        assert field_name == "status"
        assert len(missing) == 1
        assert missing[0]["value"] == "pending"

    def test_below_threshold_no_match(self, choice_processor, create_choice, hardcoded_values):
        """Test that low overlap doesn't match (below 2/3 threshold)."""
        create_choice("status", "open", "Open")
        # 1 match out of 4 = 0.25 Jaccard, well below 2/3 threshold
        hardcoded = hardcoded_values(
            ("open", "Open"), ("closed", "Closed"), ("pending", "Pending"), ("archived", "Archived")
        )

        match = choice_processor.find_matching_choice_field("status", hardcoded)

        # Jaccard: intersection=1, union=4, score=0.25 < MATCH_THRESHOLD (2/3)
        assert match is None

    def test_normalized_matching(self, choice_processor, create_choice_field, hardcoded_values):
        """Test that matching works with different casing/separators."""
        create_choice_field("priority_level", [("HIGH_PRIORITY", "High Priority"), ("low-priority", "Low Priority")])
        # Different formats should still match after normalization
        hardcoded = hardcoded_values(("high priority", "High Priority"), ("Low_Priority", "Low Priority"))

        match = choice_processor.find_matching_choice_field("priority_level", hardcoded)

        assert match is not None
        field_name, score, missing = match
        assert field_name == "priority_level"
        assert missing == []

    def test_no_match_found(self, choice_processor, create_choice, hardcoded_values):
        """Test when no existing field matches."""
        create_choice("unrelated", "value1", "Value 1")
        hardcoded = hardcoded_values(("completely", "Completely"), ("different", "Different"))

        match = choice_processor.find_matching_choice_field("new_field", hardcoded)

        assert match is None


@pytest.mark.django_db
class TestProcessSingleField:
    """Tests for process_single_field method."""

    def test_no_match_proposes_new_field(self, choice_processor_with_event_type, hardcoded_values):
        processor = choice_processor_with_event_type("fire_rep")
        hardcoded = hardcoded_values(("minor", "Minor"), ("major", "Major"))

        result = processor.process_single_field("severity", {"title": "Severity Level"}, hardcoded)

        assert result.status == "to_create"
        assert result.proposed_name is not None
        assert result.existing_choice_field is None

    def test_exact_match_returns_matched(self, choice_processor, create_choice_field, hardcoded_values):
        create_choice_field("outcome", [("success", "Success"), ("failure", "Failure")])
        hardcoded = hardcoded_values(("success", "Success"), ("failure", "Failure"))

        result = choice_processor.process_single_field("outcome", {}, hardcoded)

        assert result.status == "matched"
        assert result.existing_choice_field == "outcome"
        assert result.values_to_add == []

    def test_match_with_additions(self, choice_processor, create_choice_field, hardcoded_values):
        create_choice_field("category", [("cat_a", "Category A"), ("cat_b", "Category B")])
        # 2 existing + 1 new = 2/3 overlap (meets threshold)
        hardcoded = hardcoded_values(("cat_a", "Category A"), ("cat_b", "Category B"), ("cat_new", "New Category"))

        result = choice_processor.process_single_field("category", {}, hardcoded)

        assert result.status == "candidate"
        assert result.existing_choice_field == "category"
        assert len(result.values_to_add) == 1


@pytest.mark.django_db
class TestCreateChoiceField:
    """Tests for create_choice_field method."""

    def test_creates_choice_objects(self, choice_processor, hardcoded_values):
        values = hardcoded_values(("red", "Red Color"), ("blue", "Blue Color"))

        choice_processor.create_choice_field("colors", values)

        choices = Choice.objects.filter(field="colors").order_by("ordernum")
        assert choices.count() == 2
        assert choices[0].value == "red"
        assert choices[0].display == "Red Color"
        assert choices[0].ordernum == 0
        assert choices[1].value == "blue"
        assert choices[1].display == "Blue Color"
        assert choices[1].ordernum == 1

    def test_skips_empty_values(self, choice_processor):
        values = [{"value": "valid", "display": "Valid"}, {"value": "", "display": "Empty"}]

        choice_processor.create_choice_field("test_field", values)

        choices = Choice.objects.filter(field="test_field")
        assert choices.count() == 1
        assert choices[0].value == "valid"


@pytest.mark.django_db
class TestAddValuesToChoiceField:
    """Tests for add_values_to_choice_field method."""

    def test_adds_new_values(self, choice_processor, create_choice_field, hardcoded_values):
        create_choice_field("sizes", [("small", "Small"), ("medium", "Medium")])
        new_values = hardcoded_values(("large", "Large"), ("xlarge", "Extra Large"))

        added = choice_processor.add_values_to_choice_field("sizes", new_values)

        assert added == 2
        choices = Choice.objects.filter(field="sizes").order_by("ordernum")
        assert choices.count() == 4
        assert choices[2].value == "large"
        assert choices[2].ordernum == 2
        assert choices[3].value == "xlarge"
        assert choices[3].ordernum == 3

    def test_skips_existing_values(self, choice_processor, create_choice, hardcoded_values):
        create_choice("status", "active", "Active")
        values = hardcoded_values(("active", "Active"), ("inactive", "Inactive"))

        added = choice_processor.add_values_to_choice_field("status", values)

        assert added == 1
        assert Choice.objects.filter(field="status").count() == 2


@pytest.mark.django_db
class TestProcessHardcodedChoices:
    """Tests for the main process_hardcoded_choices method."""

    def test_processes_multiple_fields(self, choice_processor_with_event_type, v2_schema_with_fields):
        processor = choice_processor_with_event_type("test_event")
        v2_schema = v2_schema_with_fields(
            {
                "priority": [("high", "High"), ("low", "Low")],
                "status": [("open", "Open"), ("closed", "Closed")],
                "description": {"type": "string"},  # Not a choice field
            }
        )

        result_schema, metadata = processor.process_hardcoded_choices(v2_schema)

        assert len(metadata["fields"]) == 2
        assert metadata["summary"]["to_create"] == 2
        field_names = {f["field_name"] for f in metadata["fields"]}
        assert field_names == {"priority", "status"}

    def test_ignores_non_choice_fields(self, choice_processor, v2_schema_with_fields):
        v2_schema = v2_schema_with_fields(
            {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            }
        )

        _, metadata = choice_processor.process_hardcoded_choices(v2_schema)

        assert metadata["fields"] == []
        assert metadata["summary"]["to_create"] == 0

    def test_summary_tracks_matched_status(self, choice_processor, create_choice_field, v2_schema_with_fields):
        """Test that exact matches are tracked in summary."""
        create_choice_field("priority", [("high", "High"), ("low", "Low")])
        v2_schema = v2_schema_with_fields({"priority": [("high", "High"), ("low", "Low")]})

        _, metadata = choice_processor.process_hardcoded_choices(v2_schema)

        assert metadata["summary"]["matched"] == 1
        assert metadata["summary"]["candidate"] == 0
        assert metadata["summary"]["to_create"] == 0

    def test_summary_tracks_candidate_status(self, choice_processor, create_choice_field, v2_schema_with_fields):
        """Test that partial matches (candidate) are tracked in summary."""
        create_choice_field("status", [("open", "Open"), ("closed", "Closed")])
        v2_schema = v2_schema_with_fields({"status": [("open", "Open"), ("closed", "Closed"), ("pending", "Pending")]})

        _, metadata = choice_processor.process_hardcoded_choices(v2_schema)

        assert metadata["summary"]["matched"] == 0
        assert metadata["summary"]["candidate"] == 1
        assert metadata["summary"]["to_create"] == 0


@pytest.mark.django_db
class TestGenerateUniqueName:
    """Tests for generate_unique_name method."""

    def test_uses_field_name_when_available(self, choice_processor):
        name = choice_processor.generate_unique_name("my_field", {})
        assert name == "my_field"

    def test_uses_title_when_field_name_taken(self, choice_processor, create_choice):
        create_choice("my_field", "val", "Val")

        name = choice_processor.generate_unique_name("my_field", {"title": "Better Name"})
        assert name == "better_name"

    def test_uses_event_type_prefix_when_others_taken(self, choice_processor_with_event_type, create_choice):
        create_choice("status", "val", "Val")
        create_choice("current_status", "val", "Val")

        processor = choice_processor_with_event_type("fire_rep")
        name = processor.generate_unique_name("status", {"title": "Current Status"})
        assert name == "fire_rep_status"

    def test_adds_numeric_suffix_when_all_taken(self, choice_processor_with_event_type, create_choice):
        create_choice("status", "val", "Val")
        create_choice("fire_status", "val", "Val")

        processor = choice_processor_with_event_type("fire")
        name = processor.generate_unique_name("status", {"title": "Fire Status"})
        assert name == "status_1"
