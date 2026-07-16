from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from django.core.management import call_command

from activity.management.commands.repair_cameratrap_tags import (
    GOOD_COUNT_UI_FIELD,
    GOOD_TAG_COUNT_ARRAY_JSON_PROPERTY,
    GOOD_TAG_COUNT_ARRAY_V1_DEFINITION_ENTRY,
    GOOD_TAG_COUNT_ARRAY_V1_SCHEMA_PROPERTY,
    GOOD_TAG_UI_FIELD,
    GOOD_TAGS_JSON_PROPERTY,
    GOOD_TAGS_UI_FIELD_BASE,
    GOOD_TAGS_V1_DEFINITION_ENTRY,
    GOOD_TAGS_V1_SCHEMA_PROPERTY,
)
from activity.models import EventType
from choices.models import Choice
from factories import EventCategoryFactory, EventTypeFactory

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Paths to fixture files
# ---------------------------------------------------------------------------
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "eventtypes"
_REPAIR_SAMPLES_PATH = _FIXTURE_DIR / "cameratrap_rep_repair_samples.json"
_CHOICES_FIXTURE_PATH = _FIXTURE_DIR / "cameratrap_rep_choices.json"


def _load_broken_schema() -> dict:
    """Return the broken V2 schema from sample_1 of the repair samples fixture."""
    with _REPAIR_SAMPLES_PATH.open() as fh:
        samples = json.load(fh)
    return samples["sample_1"]


def _load_broken_schema_without_tag_count_array() -> dict:
    """Return a V2 schema with tags broken AND tag_count_array removed."""
    schema = copy.deepcopy(_load_broken_schema())
    # Remove tag_count_array from json properties.
    schema["json"]["properties"].pop("tag_count_array", None)
    # Remove tag_count_array ui fields.
    schema["ui"]["fields"].pop("tag_count_array", None)
    schema["ui"]["fields"].pop("tag", None)
    schema["ui"]["fields"].pop("count", None)
    # Remove any section column references to tag_count_array.
    for section in schema["ui"]["sections"].values():
        for col in ("leftColumn", "rightColumn"):
            section[col] = [
                entry
                for entry in section.get(col, [])
                if not (isinstance(entry, dict) and entry.get("name") == "tag_count_array")
            ]
    return schema


def _load_choices_fixture() -> list[dict]:
    """Return all choice entries from the choices fixture."""
    with _CHOICES_FIXTURE_PATH.open() as fh:
        return json.load(fh)


def _make_cameratrap_event_type(schema: dict) -> EventType:
    """Create a V2 cameratrap_rep EventType with the given schema dict."""
    category = EventCategoryFactory.create(value="camera_trap_cat")
    return EventTypeFactory.create(
        value="cameratrap_rep",
        display="Camera Trap Report",
        version=EventType.VersionChoices.VERSION_2,
        schema=json.dumps(schema),
        category=category,
    )


def _load_v1_broken_schema() -> dict:
    """Return the broken V1 schema from v1_sample_1 of the repair samples fixture."""
    with _REPAIR_SAMPLES_PATH.open() as fh:
        samples = json.load(fh)
    return samples["v1_sample_1"]


def _load_v1_broken_schema_without_tag_count_array() -> dict:
    """Return a V1 schema with tags broken AND tag_count_array removed."""
    schema = copy.deepcopy(_load_v1_broken_schema())
    # Remove tag_count_array from schema.properties.
    schema["schema"]["properties"].pop("tag_count_array", None)
    # Remove tag_count_array from definition.
    schema["definition"] = [entry for entry in schema["definition"] if entry.get("key") != "tag_count_array"]
    return schema


def _make_cameratrap_v1_event_type(schema: dict) -> EventType:
    """Create a V1 cameratrap_rep EventType with the given schema dict."""
    category = EventCategoryFactory.create(value="camera_trap_cat")
    return EventTypeFactory.create(
        value="cameratrap_rep",
        display="Camera Trap Report",
        version=EventType.VersionChoices.VERSION_1,
        schema=json.dumps(schema),
        category=category,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCameratrapV2Tags:
    def test_broken_schema_gets_json_tags_fixed(self):
        """json.properties.tags is replaced with the known-good array shape."""
        broken_schema = _load_broken_schema()
        event_type = _make_cameratrap_event_type(broken_schema)

        # Precondition: the fixture schema has a broken string-type tags field.
        pre_schema = json.loads(event_type.schema)
        assert pre_schema["json"]["properties"]["tags"]["type"] == "string"

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        tags_json = post_schema["json"]["properties"]["tags"]

        assert tags_json["type"] == "array"
        assert tags_json == GOOD_TAGS_JSON_PROPERTY

    def test_broken_schema_gets_ui_tags_fixed_with_parent_preserved(self):
        """ui.fields.tags becomes CHOICE_LIST and the existing parent (section-3) is preserved."""
        broken_schema = _load_broken_schema()
        event_type = _make_cameratrap_event_type(broken_schema)

        # sample_1 has tags parented to section-3
        pre_schema = json.loads(event_type.schema)
        assert pre_schema["ui"]["fields"]["tags"]["parent"] == "section-3"

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        ui_tags = post_schema["ui"]["fields"]["tags"]

        assert ui_tags["type"] == "CHOICE_LIST"
        assert ui_tags["inputType"] == "LIST"
        assert ui_tags["choices"] == GOOD_TAGS_UI_FIELD_BASE["choices"]
        # Parent must be preserved as section-3, not replaced with section-2.
        assert ui_tags["parent"] == "section-3"

    def test_parent_section_becomes_active(self):
        """The parent section (section-3) was isActive=false; after repair it is true."""
        broken_schema = _load_broken_schema()
        # Sanity check: sample_1 has section-3 isActive=false
        assert broken_schema["ui"]["sections"]["section-3"]["isActive"] is False

        event_type = _make_cameratrap_event_type(broken_schema)
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["ui"]["sections"]["section-3"]["isActive"] is True

    def test_partially_repaired_schema_ui_field_gets_repaired(self):
        """A schema whose JSON tags property is already fixed but whose UI field
        is still TEXT/SHORT_TEXT is still treated as needing repair."""
        schema = _load_broken_schema()
        schema["json"]["properties"]["tags"] = dict(GOOD_TAGS_JSON_PROPERTY)
        # sample_1's ui.fields.tags is still the broken TEXT/SHORT_TEXT shape.
        event_type = _make_cameratrap_event_type(schema)

        pre_schema = json.loads(event_type.schema)
        assert pre_schema["json"]["properties"]["tags"]["type"] == "array"
        assert pre_schema["ui"]["fields"]["tags"]["type"] == "TEXT"

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        ui_tags = post_schema["ui"]["fields"]["tags"]

        assert ui_tags["type"] == "CHOICE_LIST"
        assert ui_tags["inputType"] == "LIST"
        assert ui_tags["choices"] == GOOD_TAGS_UI_FIELD_BASE["choices"]
        assert ui_tags["parent"] == "section-3"

    def test_other_schema_properties_are_untouched(self):
        """Fields other than `tags` are not modified by the repair command."""
        broken_schema = _load_broken_schema()
        event_type = _make_cameratrap_event_type(broken_schema)
        pre_schema = json.loads(event_type.schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)

        # JSON schema: all non-tags properties must be identical.
        for key in pre_schema["json"]["properties"]:
            if key == "tags":
                continue
            assert (
                post_schema["json"]["properties"][key] == pre_schema["json"]["properties"][key]
            ), f"JSON property {key!r} was unexpectedly modified"

        # UI fields: all non-tags fields must be identical.
        for key in pre_schema["ui"]["fields"]:
            if key == "tags":
                continue
            assert (
                post_schema["ui"]["fields"][key] == pre_schema["ui"]["fields"][key]
            ), f"UI field {key!r} was unexpectedly modified"

        # Sections other than section-3 must be identical (section-3 only has isActive changed).
        for section_key, section_val in pre_schema["ui"]["sections"].items():
            if section_key == "section-3":
                continue
            assert (
                post_schema["ui"]["sections"][section_key] == section_val
            ), f"UI section {section_key!r} was unexpectedly modified"

        # UI order is unchanged.
        assert post_schema["ui"]["order"] == pre_schema["ui"]["order"]

    def test_choices_are_created(self):
        """After repair, choices from the fixture are created in the DB for the tenant."""
        broken_schema = _load_broken_schema()
        _make_cameratrap_event_type(broken_schema)

        # No choices before command runs.
        assert Choice.objects.filter(field="cameratrap_tags").count() == 0

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        expected_count = len(_load_choices_fixture())
        actual_count = Choice.objects.filter(field="cameratrap_tags").count()
        assert actual_count == expected_count

        # Spot-check a couple of specific values.
        assert Choice.objects.filter(field="cameratrap_tags", value="lion").exists()
        assert Choice.objects.filter(field="cameratrap_tags", value="elephant").exists()

    def test_choices_display_values(self):
        """Spot-check that choice display names are set correctly from the fixture."""
        broken_schema = _load_broken_schema()
        _make_cameratrap_event_type(broken_schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        lion = Choice.objects.get(field="cameratrap_tags", value="lion")
        assert lion.display == "Lion"
        assert lion.is_active is True

    def test_rerunning_command_does_not_duplicate_choices(self):
        """Running the command twice does not create duplicate choices (idempotency)."""
        broken_schema = _load_broken_schema()
        _make_cameratrap_event_type(broken_schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        count_after_first = Choice.objects.filter(field="cameratrap_tags").count()

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        count_after_second = Choice.objects.filter(field="cameratrap_tags").count()

        assert count_after_first == count_after_second

    def test_already_good_schema_is_a_noop(self):
        """Running the command on an already-repaired schema makes no schema change."""
        broken_schema = _load_broken_schema()
        event_type = _make_cameratrap_event_type(broken_schema)

        # First run repairs it.
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        event_type.refresh_from_db()
        schema_after_first = event_type.schema

        # Second run should be a no-op for the schema.
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        event_type.refresh_from_db()
        schema_after_second = event_type.schema

        assert json.loads(schema_after_first) == json.loads(schema_after_second)

    def test_dry_run_does_not_change_schema(self):
        """--dry-run leaves EventType.schema unchanged."""
        broken_schema = _load_broken_schema()
        event_type = _make_cameratrap_event_type(broken_schema)
        original_schema = event_type.schema

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep", dry_run=True)

        event_type.refresh_from_db()
        assert event_type.schema == original_schema

    def test_dry_run_does_not_create_choices(self):
        """--dry-run creates no Choice rows."""
        broken_schema = _load_broken_schema()
        _make_cameratrap_event_type(broken_schema)

        count_before = Choice.objects.filter(field="cameratrap_tags").count()
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep", dry_run=True)
        count_after = Choice.objects.filter(field="cameratrap_tags").count()

        assert count_before == count_after == 0

    def test_no_event_type_found_exits_cleanly(self):
        """Command exits cleanly when no matching V2 event type exists."""
        # No event type created — should not raise.
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        # If we got here without exception, the test passes.

    def test_schema_hash_cache_is_invalidated_after_repair(self):
        """After repair, the schema_hash:<value> cache key is deleted."""
        broken_schema = _load_broken_schema()
        _make_cameratrap_event_type(broken_schema)

        with patch("activity.management.commands.repair_cameratrap_tags.cache") as mock_cache:
            call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        mock_cache.delete.assert_called_with("schema_hash:cameratrap_rep")

    def test_choices_only_path_invalidates_cache_when_new_choices_are_created(self):
        """When the schema is already good but choices are missing, installing
        them must invalidate the schema_hash cache key (ETags would otherwise
        stay stale until the cache entry's TTL expires)."""
        schema = _load_broken_schema()
        schema["json"]["properties"]["tags"] = dict(GOOD_TAGS_JSON_PROPERTY)
        schema["ui"]["fields"]["tags"] = {**GOOD_TAGS_UI_FIELD_BASE, "parent": "section-3"}
        _make_cameratrap_event_type(schema)

        assert Choice.objects.filter(field="cameratrap_tags").count() == 0

        with patch("activity.management.commands.repair_cameratrap_tags.cache") as mock_cache:
            call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        mock_cache.delete.assert_called_with("schema_hash:cameratrap_rep")
        assert Choice.objects.filter(field="cameratrap_tags").count() > 0

    def test_choices_only_path_does_not_invalidate_cache_when_no_new_choices(self):
        """When the schema is already good AND choices are already installed,
        no cache invalidation is necessary."""
        schema = _load_broken_schema()
        schema["json"]["properties"]["tags"] = dict(GOOD_TAGS_JSON_PROPERTY)
        schema["ui"]["fields"]["tags"] = {**GOOD_TAGS_UI_FIELD_BASE, "parent": "section-3"}
        _make_cameratrap_event_type(schema)

        # Pre-install the choices so the second run creates nothing new.
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        with patch("activity.management.commands.repair_cameratrap_tags.cache") as mock_cache:
            call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        mock_cache.delete.assert_not_called()

    def test_choices_only_path_install_is_atomic_on_failure(self):
        """If `_install_choices` fails partway through the fixture, the
        choices-only path's writes must be rolled back (wrapped in
        `transaction.atomic()`) rather than leaving a partially-installed
        choice list."""
        schema = _load_broken_schema()
        schema["json"]["properties"]["tags"] = dict(GOOD_TAGS_JSON_PROPERTY)
        schema["ui"]["fields"]["tags"] = {**GOOD_TAGS_UI_FIELD_BASE, "parent": "section-3"}
        _make_cameratrap_event_type(schema)

        original_update_or_create = Choice.objects.update_or_create
        call_count = {"n": 0}

        def flaky_update_or_create(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom")
            return original_update_or_create(*args, **kwargs)

        with patch.object(Choice.objects, "update_or_create", side_effect=flaky_update_or_create):
            with pytest.raises(RuntimeError, match="boom"):
                call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        assert Choice.objects.filter(field="cameratrap_tags").count() == 0


# ---------------------------------------------------------------------------
# V2 tag_count_array tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCameratrapV2TagCountArray:
    def test_missing_tag_count_array_json_property_is_added(self):
        """json.properties.tag_count_array is added when absent, matching the canonical constant."""
        schema = _load_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_event_type(schema)

        # Precondition: tag_count_array is absent.
        pre_schema = json.loads(event_type.schema)
        assert "tag_count_array" not in pre_schema["json"]["properties"]

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tag_count_array"] == GOOD_TAG_COUNT_ARRAY_JSON_PROPERTY

    def test_missing_tag_count_array_ui_fields_are_added(self):
        """ui.fields entries tag_count_array, tag, and count are added when absent."""
        schema = _load_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        ui_fields = post_schema["ui"]["fields"]

        # Collection field — check shape excluding parent (parent is set dynamically).
        tca_field = ui_fields["tag_count_array"]
        assert tca_field["type"] == "COLLECTION"
        assert tca_field["itemName"] == "Detection"
        assert tca_field["leftColumn"] == ["tag", "count"]
        assert tca_field["rightColumn"] == []
        assert "parent" in tca_field

        # Sub-fields must match the canonical constants.
        assert ui_fields["tag"] == GOOD_TAG_UI_FIELD
        assert ui_fields["count"] == GOOD_COUNT_UI_FIELD

    def test_missing_tag_count_array_collection_parent_set_and_section_made_active(self):
        """When tag_count_array is added, its parent section is set and isActive is True."""
        schema = _load_broken_schema_without_tag_count_array()
        # section-2 exists in the sample schema; use it as the expected parent.
        assert "section-2" in schema["ui"]["sections"]
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        tca_field = post_schema["ui"]["fields"]["tag_count_array"]
        assert tca_field["parent"] == "section-2"
        assert post_schema["ui"]["sections"]["section-2"]["isActive"] is True

    def test_missing_tag_count_array_column_reference_added_to_section(self):
        """A column reference for tag_count_array is added to the parent section."""
        schema = _load_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        tca_field = post_schema["ui"]["fields"]["tag_count_array"]
        parent = tca_field["parent"]
        section = post_schema["ui"]["sections"][parent]

        all_column_names = [
            entry["name"]
            for col in ("leftColumn", "rightColumn")
            for entry in section.get(col, [])
            if isinstance(entry, dict)
        ]
        assert "tag_count_array" in all_column_names

    def test_present_tag_count_array_is_left_untouched(self):
        """When tag_count_array already exists in json.properties it is not overwritten."""
        # Use the standard broken sample which already has tag_count_array (but tags is broken).
        schema = _load_broken_schema()
        original_tca = copy.deepcopy(schema["json"]["properties"]["tag_count_array"])
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tag_count_array"] == original_tca

    def test_tags_already_good_but_tag_count_array_missing_still_repaired(self):
        """A schema with correct tags but missing tag_count_array still gets tag_count_array added."""
        schema = _load_broken_schema_without_tag_count_array()
        # Pre-fix the tags field so it is already correct.
        schema["json"]["properties"]["tags"] = dict(GOOD_TAGS_JSON_PROPERTY)
        schema["ui"]["fields"]["tags"] = {**GOOD_TAGS_UI_FIELD_BASE, "parent": "section-3"}

        event_type = _make_cameratrap_event_type(schema)

        # Precondition: tags is good, tag_count_array is missing.
        pre_schema = json.loads(event_type.schema)
        assert pre_schema["json"]["properties"]["tags"]["type"] == "array"
        assert "tag_count_array" not in pre_schema["json"]["properties"]

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tag_count_array"] == GOOD_TAG_COUNT_ARRAY_JSON_PROPERTY

    def test_rerunning_is_idempotent_for_tag_count_array(self):
        """Running the command twice leaves tag_count_array unchanged after first run."""
        schema = _load_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        event_type.refresh_from_db()
        schema_after_first = json.loads(event_type.schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        event_type.refresh_from_db()
        schema_after_second = json.loads(event_type.schema)

        assert schema_after_first == schema_after_second

    def test_rerunning_does_not_duplicate_section_column_reference(self):
        """Running the command twice does not add a duplicate tag_count_array section reference."""
        schema = _load_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        tca_parent = post_schema["ui"]["fields"]["tag_count_array"]["parent"]
        section = post_schema["ui"]["sections"][tca_parent]

        tca_references = [
            entry
            for col in ("leftColumn", "rightColumn")
            for entry in section.get(col, [])
            if isinstance(entry, dict) and entry.get("name") == "tag_count_array"
        ]
        assert len(tca_references) == 1


# ---------------------------------------------------------------------------
# V2 UI parent fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCameratrapV2SectionFallback:
    def test_falls_back_to_last_existing_section_when_order_entry_missing(self):
        """When section-2 does not exist and the existing/last `ui.order` entry
        also does not exist in `ui.sections`, the command falls back to the
        last entry of `ui.order` that IS present, rather than pointing the
        parent at a nonexistent section."""
        schema = _load_broken_schema()
        # Remove the FALLBACK_PARENT_SECTION and point tags' existing parent at
        # a section that no longer exists.
        schema["ui"]["sections"].pop("section-2", None)
        schema["ui"]["fields"]["tags"]["parent"] = "section-missing"
        # The last order entry ("section-bogus") is not in ui.sections, but
        # "section-1" (earlier in order) is.
        schema["ui"]["order"] = ["section-1", "section-bogus"]
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["ui"]["fields"]["tags"]["parent"] == "section-1"
        assert post_schema["ui"]["sections"]["section-1"]["isActive"] is True


# ---------------------------------------------------------------------------
# V2 defensive-schema tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCameratrapV2DefensiveSchema:
    def test_missing_json_and_ui_keys_does_not_raise(self):
        """A V2 schema missing the top-level "json" and "ui" keys entirely is
        repaired in place rather than raising a KeyError."""
        event_type = _make_cameratrap_event_type({})

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tags"] == GOOD_TAGS_JSON_PROPERTY
        assert post_schema["ui"]["fields"]["tags"]["type"] == "CHOICE_LIST"
        assert post_schema["json"]["properties"]["tag_count_array"] == GOOD_TAG_COUNT_ARRAY_JSON_PROPERTY

    def test_missing_sections_repaired_schema_is_internally_consistent(self):
        """When a V2 schema has no `ui.sections` (and no `ui.order`) at all,
        repair must create the fallback parent section rather than leaving
        `tags` / `tag_count_array` pointed at a section that doesn't exist."""
        event_type = _make_cameratrap_event_type({})

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        ui = post_schema["ui"]

        tags_parent = ui["fields"]["tags"]["parent"]
        tca_parent = ui["fields"]["tag_count_array"]["parent"]

        # The parent section referenced by each field must actually exist,
        # be part of ui.order, and be active.
        assert tags_parent in ui["sections"]
        assert tca_parent in ui["sections"]
        assert tags_parent in ui["order"]
        assert tca_parent in ui["order"]
        assert ui["sections"][tags_parent]["isActive"] is True
        assert ui["sections"][tca_parent]["isActive"] is True

        # The tag_count_array column reference must be present in the
        # newly-created section.
        tca_column_names = [
            entry["name"]
            for col in ("leftColumn", "rightColumn")
            for entry in ui["sections"][tca_parent].get(col, [])
            if isinstance(entry, dict)
        ]
        assert "tag_count_array" in tca_column_names

    def test_missing_ui_order_key_does_not_raise_and_gets_populated(self):
        """A schema with `ui.sections` present but empty, and no `ui.order`
        key at all, still repairs cleanly: the newly-created fallback
        section is appended to a freshly-created `ui.order`."""
        schema = _load_broken_schema()
        del schema["ui"]["order"]
        schema["ui"]["sections"] = {}

        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        ui = post_schema["ui"]

        tags_parent = ui["fields"]["tags"]["parent"]
        assert tags_parent in ui["sections"]
        assert "order" in ui
        assert tags_parent in ui["order"]
        assert ui["sections"][tags_parent]["isActive"] is True

    def test_non_dict_ui_value_is_coerced_and_repaired(self):
        """A schema with `"ui": null` does not raise an AttributeError; `ui`
        is coerced to a dict and the schema is repaired normally."""
        event_type = _make_cameratrap_event_type({"ui": None})

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tags"] == GOOD_TAGS_JSON_PROPERTY
        assert post_schema["ui"]["fields"]["tags"]["type"] == "CHOICE_LIST"
        tags_parent = post_schema["ui"]["fields"]["tags"]["parent"]
        assert tags_parent in post_schema["ui"]["sections"]
        assert tags_parent in post_schema["ui"]["order"]

    def test_non_dict_json_value_is_coerced_and_repaired(self):
        """A schema with `"json": []` does not raise an AttributeError; `json`
        is coerced to a dict and the schema is repaired normally."""
        event_type = _make_cameratrap_event_type({"json": []})

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tags"] == GOOD_TAGS_JSON_PROPERTY
        assert post_schema["ui"]["fields"]["tags"]["type"] == "CHOICE_LIST"

    def test_non_dict_nested_containers_are_coerced_and_repaired(self):
        """Non-dict/non-list nested containers that the command chains
        `.setdefault()` on (json.properties, ui.fields, ui.sections,
        ui.order) are coerced to the expected empty container rather than
        raising an AttributeError."""
        schema = {
            "json": {"properties": []},
            "ui": {"fields": None, "sections": [], "order": {}},
        }
        event_type = _make_cameratrap_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["json"]["properties"]["tags"] == GOOD_TAGS_JSON_PROPERTY
        assert post_schema["ui"]["fields"]["tags"]["type"] == "CHOICE_LIST"
        assert isinstance(post_schema["ui"]["sections"], dict)
        assert isinstance(post_schema["ui"]["order"], list)
        tags_parent = post_schema["ui"]["fields"]["tags"]["parent"]
        assert tags_parent in post_schema["ui"]["sections"]
        assert tags_parent in post_schema["ui"]["order"]


def _make_repaired_v1_schema() -> dict:
    """Return a V1 schema that is already in the repaired shape."""
    schema = _load_v1_broken_schema()
    schema["schema"]["properties"]["tags"] = dict(GOOD_TAGS_V1_SCHEMA_PROPERTY)
    schema["definition"].append(dict(GOOD_TAGS_V1_DEFINITION_ENTRY))
    return schema


def _tags_definition_entries(schema: dict) -> list[dict]:
    """Return all definition entries whose key is 'tags'."""
    return [entry for entry in schema["definition"] if entry.get("key") == "tags"]


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCameratrapV1Tags:
    def test_broken_v1_tags_schema_property_is_fixed(self):
        """schema.properties.tags is replaced with the known-good choice-list reference shape."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        # Precondition: the fixture schema has a broken string-type tags field.
        pre_schema = json.loads(event_type.schema)
        assert pre_schema["schema"]["properties"]["tags"]["type"] == "string"

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["schema"]["properties"]["tags"] == GOOD_TAGS_V1_SCHEMA_PROPERTY

    def test_broken_v1_tags_definition_entry_is_appended(self):
        """A tags entry matching the known-good definition is appended to definition."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        # Precondition: no tags entry exists in the definition.
        pre_schema = json.loads(event_type.schema)
        assert _tags_definition_entries(pre_schema) == []

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert GOOD_TAGS_V1_DEFINITION_ENTRY in post_schema["definition"]

    def test_rerunning_v1_command_is_idempotent_no_duplicate_definition_entry(self):
        """Running the command twice yields exactly one tags definition entry."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert len(_tags_definition_entries(post_schema)) == 1

    def test_rerunning_v1_command_is_idempotent_no_schema_change(self):
        """Running the command twice leaves the schema identical to the first run."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        event_type.refresh_from_db()
        schema_after_first = event_type.schema

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        event_type.refresh_from_db()
        schema_after_second = event_type.schema

        assert json.loads(schema_after_first) == json.loads(schema_after_second)

    def test_already_good_v1_schema_is_a_noop(self):
        """Running the command on an already-repaired V1 schema makes no schema change."""
        event_type = _make_cameratrap_v1_event_type(_make_repaired_v1_schema())
        original_schema = event_type.schema

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        assert json.loads(event_type.schema) == json.loads(original_schema)

    def test_v1_dry_run_does_not_change_schema(self):
        """--dry-run leaves EventType.schema unchanged for V1."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())
        original_schema = event_type.schema

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep", dry_run=True)

        event_type.refresh_from_db()
        assert event_type.schema == original_schema

    def test_v1_dry_run_does_not_create_choices(self):
        """--dry-run creates no Choice rows for V1."""
        _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        count_before = Choice.objects.filter(field="cameratrap_tags").count()
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep", dry_run=True)
        count_after = Choice.objects.filter(field="cameratrap_tags").count()

        assert count_before == count_after == 0

    def test_v1_choices_are_created(self):
        """After V1 repair, choices from the fixture are created in the DB for the tenant."""
        _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        assert Choice.objects.filter(field="cameratrap_tags").count() == 0

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        expected_count = len(_load_choices_fixture())
        assert Choice.objects.filter(field="cameratrap_tags").count() == expected_count

    def test_v1_schema_hash_cache_is_invalidated(self):
        """After V1 repair, the schema_hash:<value> cache key is deleted."""
        _make_cameratrap_v1_event_type(_load_v1_broken_schema())

        with patch("activity.management.commands.repair_cameratrap_tags.cache") as mock_cache:
            call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        mock_cache.delete.assert_called_with("schema_hash:cameratrap_rep")

    def test_v1_non_tags_properties_are_untouched(self):
        """Properties other than `tags` are not modified by the V1 repair."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())
        pre_schema = json.loads(event_type.schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)

        for key in pre_schema["schema"]["properties"]:
            if key == "tags":
                continue
            assert (
                post_schema["schema"]["properties"][key] == pre_schema["schema"]["properties"][key]
            ), f"V1 property {key!r} was unexpectedly modified"

    def test_v1_non_tags_definition_entries_are_untouched(self):
        """Definition entries other than the tags entry are not modified by the V1 repair."""
        event_type = _make_cameratrap_v1_event_type(_load_v1_broken_schema())
        pre_schema = json.loads(event_type.schema)
        pre_non_tags = [entry for entry in pre_schema["definition"] if entry.get("key") != "tags"]

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        post_non_tags = [entry for entry in post_schema["definition"] if entry.get("key") != "tags"]

        assert post_non_tags == pre_non_tags

    def test_v1_schema_missing_properties_reports_error_without_raising(self):
        """A V1 schema missing schema.properties is left untouched and reported
        as an error rather than raising a KeyError."""
        broken_schema = {"schema": {}, "definition": []}
        event_type = _make_cameratrap_v1_event_type(broken_schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        assert json.loads(event_type.schema) == broken_schema

    def test_v1_schema_missing_definition_reports_error_without_raising(self):
        """A V1 schema missing the top-level definition key is left untouched
        and reported as an error rather than raising a KeyError."""
        broken_schema = {"schema": {"properties": {}}}
        event_type = _make_cameratrap_v1_event_type(broken_schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        assert json.loads(event_type.schema) == broken_schema

    def test_v1_choices_only_path_install_is_atomic_on_failure(self):
        """If `_install_choices` fails partway through the fixture on the V1
        choices-only path (tags and tag_count_array both already correct),
        the writes must be rolled back (wrapped in `transaction.atomic()`)
        rather than leaving a partially-installed choice list."""
        _make_cameratrap_v1_event_type(_make_repaired_v1_schema())

        original_update_or_create = Choice.objects.update_or_create
        call_count = {"n": 0}

        def flaky_update_or_create(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom")
            return original_update_or_create(*args, **kwargs)

        with patch.object(Choice.objects, "update_or_create", side_effect=flaky_update_or_create):
            with pytest.raises(RuntimeError, match="boom"):
                call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        assert Choice.objects.filter(field="cameratrap_tags").count() == 0


# ---------------------------------------------------------------------------
# V1 tag_count_array tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCameratrapV1TagCountArray:
    def test_missing_tag_count_array_schema_property_is_added(self):
        """schema.properties.tag_count_array is added when absent."""
        schema = _load_v1_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_v1_event_type(schema)

        # Precondition: tag_count_array is absent.
        pre_schema = json.loads(event_type.schema)
        assert "tag_count_array" not in pre_schema["schema"]["properties"]

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["schema"]["properties"]["tag_count_array"] == GOOD_TAG_COUNT_ARRAY_V1_SCHEMA_PROPERTY

    def test_missing_tag_count_array_definition_entry_is_appended(self):
        """A tag_count_array definition entry is appended when absent."""
        schema = _load_v1_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_v1_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        tca_entries = [e for e in post_schema["definition"] if e.get("key") == "tag_count_array"]
        assert len(tca_entries) == 1
        assert tca_entries[0] == GOOD_TAG_COUNT_ARRAY_V1_DEFINITION_ENTRY

    def test_rerunning_v1_tag_count_array_is_idempotent(self):
        """Running the command twice yields exactly one tag_count_array definition entry."""
        schema = _load_v1_broken_schema_without_tag_count_array()
        event_type = _make_cameratrap_v1_event_type(schema)

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")
        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        tca_entries = [e for e in post_schema["definition"] if e.get("key") == "tag_count_array"]
        assert len(tca_entries) == 1

    def test_v1_tags_already_good_but_tag_count_array_missing_still_repaired(self):
        """A V1 schema with correct tags but missing tag_count_array still gets tag_count_array added."""
        schema = _load_v1_broken_schema_without_tag_count_array()
        # Pre-fix tags to the correct shape.
        schema["schema"]["properties"]["tags"] = dict(GOOD_TAGS_V1_SCHEMA_PROPERTY)
        schema["definition"].append(dict(GOOD_TAGS_V1_DEFINITION_ENTRY))

        event_type = _make_cameratrap_v1_event_type(schema)

        # Precondition: tags is good, tag_count_array is missing.
        pre_schema = json.loads(event_type.schema)
        assert pre_schema["schema"]["properties"]["tags"] == GOOD_TAGS_V1_SCHEMA_PROPERTY
        assert "tag_count_array" not in pre_schema["schema"]["properties"]

        call_command("repair_cameratrap_tags", event_type_value="cameratrap_rep")

        event_type.refresh_from_db()
        post_schema = json.loads(event_type.schema)
        assert post_schema["schema"]["properties"]["tag_count_array"] == GOOD_TAG_COUNT_ARRAY_V1_SCHEMA_PROPERTY
