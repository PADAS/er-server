from __future__ import annotations

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from activity.management.commands.fix_event_details import (
    EVENT_DETAILS_KEY,
    CoerceToType,
    Command,
    _build_coerce_type,
    _build_delete_key,
    _build_rename_key,
    _build_set_value,
    _build_unwrap_single_array,
    _build_wrap_in_array,
)
from activity.models import EventDetails
from factories import EventDetailsFactory, EventFactory, EventTypeFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ed(property_key: str, value: object) -> EventDetails:
    """Create an EventDetails with a single known property set."""
    ed = EventDetailsFactory(data={EVENT_DETAILS_KEY: {property_key: value}})
    return ed


def revision_count(ed: EventDetails) -> int:
    """Return the number of revision records for this EventDetails instance."""
    return EventDetails.revision.model.objects.filter(object_id=ed.pk).count()


# ---------------------------------------------------------------------------
# Unit tests for individual transform builders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestWrapInArrayTransform:
    def test_scalar_string_becomes_single_element_list(self) -> None:
        fn = _build_wrap_in_array("key")
        details = {"key": "hello"}
        result = fn(details)
        assert result == {"key": ["hello"]}

    def test_scalar_number_becomes_single_element_list(self) -> None:
        fn = _build_wrap_in_array("key")
        details = {"key": 42}
        result = fn(details)
        assert result == {"key": [42]}

    def test_scalar_bool_becomes_single_element_list(self) -> None:
        fn = _build_wrap_in_array("key")
        details = {"key": True}
        result = fn(details)
        assert result == {"key": [True]}

    def test_already_list_returns_none(self) -> None:
        fn = _build_wrap_in_array("key")
        details = {"key": ["already"]}
        assert fn(details) is None

    def test_does_not_mutate_original(self) -> None:
        fn = _build_wrap_in_array("key")
        details = {"key": "value", "other": "unchanged"}
        result = fn(details)
        assert details == {"key": "value", "other": "unchanged"}
        assert result is not None
        assert result["other"] == "unchanged"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUnwrapSingleArrayTransform:
    def test_single_element_list_becomes_scalar(self) -> None:
        fn = _build_unwrap_single_array("key")
        details = {"key": ["only_one"]}
        result = fn(details)
        assert result == {"key": "only_one"}

    def test_multi_element_list_returns_none(self) -> None:
        fn = _build_unwrap_single_array("key")
        details = {"key": ["a", "b"]}
        assert fn(details) is None

    def test_empty_list_returns_none(self) -> None:
        fn = _build_unwrap_single_array("key")
        details = {"key": []}
        assert fn(details) is None

    def test_scalar_value_returns_none(self) -> None:
        fn = _build_unwrap_single_array("key")
        details = {"key": "not_a_list"}
        assert fn(details) is None

    def test_does_not_mutate_original(self) -> None:
        fn = _build_unwrap_single_array("key")
        original = {"key": ["item"]}
        fn(original)
        assert original == {"key": ["item"]}


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestCoerceTypeTransform:
    def test_int_string_to_int(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        result = fn({"key": "42"})
        assert result == {"key": 42}

    def test_already_correct_type_returns_none(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        assert fn({"key": 42}) is None

    def test_number_to_string(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.STRING)
        result = fn({"key": 3})
        assert result == {"key": "3"}

    def test_unconvertable_value_returns_none(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        # "not_a_number" cannot be cast to int
        assert fn({"key": "not_a_number"}) is None

    def test_integer_coercion_rejects_bool(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        # bool is a subclass of int, but a boolean value is not a meaningful
        # integer to coerce to — it must be skipped, not silently cast to 0/1.
        assert fn({"key": True}) is None

    def test_number_coercion_with_fractional_string_yields_float(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.NUMBER)
        result = fn({"key": "3.14"})
        assert result is not None
        assert isinstance(result["key"], float)
        assert abs(result["key"] - 3.14) < 1e-9

    def test_number_coercion_with_integral_string_yields_int(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.NUMBER)
        result = fn({"key": "3"})
        assert result == {"key": 3}
        assert isinstance(result["key"], int)

    def test_number_coercion_rejects_bool(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.NUMBER)
        # bool is a subclass of int, but a boolean value is not a meaningful
        # number to coerce to — it must be skipped, not silently cast to 0/1.
        assert fn({"key": True}) is None

    def test_integer_coercion_rejects_fractional_float(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        # 3.14 has no meaningful integer representation — truncating to 3
        # would silently discard data, so this must be skipped instead.
        assert fn({"key": 3.14}) is None

    def test_integer_coercion_rejects_fractional_string(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        assert fn({"key": "3.14"}) is None

    def test_integer_coercion_accepts_integral_float(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.INTEGER)
        result = fn({"key": 3.0})
        assert result == {"key": 3}
        assert isinstance(result["key"], int)

    def test_number_coercion_preserves_fractional_float(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.NUMBER)
        # A fractional float is already a valid JSON Schema "number" — it
        # must be preserved, not truncated to an int.
        result = fn({"key": 3.14})
        assert result is None

    def test_number_coercion_of_integral_float_yields_int(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.NUMBER)
        result = fn({"key": 3.0})
        assert result == {"key": 3}
        assert isinstance(result["key"], int)

    def test_boolean_coercion_of_false_string_yields_false(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.BOOLEAN)
        result = fn({"key": "false"})
        assert result == {"key": False}
        assert isinstance(result["key"], bool)

    def test_boolean_coercion_of_true_string_yields_true(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.BOOLEAN)
        result = fn({"key": "true"})
        assert result == {"key": True}
        assert isinstance(result["key"], bool)

    def test_boolean_coercion_of_unparseable_string_returns_none(self) -> None:
        fn = _build_coerce_type("key", CoerceToType.BOOLEAN)
        # "maybe" is not a recognized boolean literal — must be skipped
        # rather than coerced to True via bool("maybe").
        assert fn({"key": "maybe"}) is None


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSetValueTransform:
    def test_replaces_existing_value(self) -> None:
        fn = _build_set_value("key", "new_value")
        result = fn({"key": "old_value"})
        assert result == {"key": "new_value"}

    def test_already_at_target_value_returns_none(self) -> None:
        fn = _build_set_value("key", "target")
        assert fn({"key": "target"}) is None

    def test_can_set_to_list(self) -> None:
        fn = _build_set_value("key", [1, 2, 3])
        result = fn({"key": "old"})
        assert result == {"key": [1, 2, 3]}

    def test_can_set_to_none(self) -> None:
        fn = _build_set_value("key", None)
        result = fn({"key": "something"})
        assert result == {"key": None}


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRenameKeyTransform:
    def test_renames_key(self) -> None:
        fn = _build_rename_key("old_key", "new_key")
        result = fn({"old_key": "value", "other": "x"})
        assert result == {"new_key": "value", "other": "x"}

    def test_skips_when_destination_already_present(self) -> None:
        fn = _build_rename_key("old_key", "new_key")
        assert fn({"old_key": "v", "new_key": "existing"}) is None

    def test_skips_when_source_absent(self) -> None:
        fn = _build_rename_key("old_key", "new_key")
        assert fn({"other": "v"}) is None

    def test_does_not_mutate_original(self) -> None:
        fn = _build_rename_key("old_key", "new_key")
        original = {"old_key": "v"}
        fn(original)
        assert "old_key" in original


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeleteKeyTransform:
    def test_removes_existing_key(self) -> None:
        fn = _build_delete_key("key")
        result = fn({"key": "value", "other": "x"})
        assert result == {"other": "x"}
        assert "key" not in result

    def test_already_absent_returns_none(self) -> None:
        fn = _build_delete_key("key")
        assert fn({"other": "value"}) is None

    def test_does_not_mutate_original(self) -> None:
        fn = _build_delete_key("key")
        original = {"key": "value"}
        fn(original)
        assert "key" in original


# ---------------------------------------------------------------------------
# Integration tests: command execution against database records
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFixEventDetailsCommand:
    # ------------------------------------------------------------------
    # wrap-in-array: happy path and idempotency
    # ------------------------------------------------------------------

    def test_wrap_in_array_transforms_scalar(self) -> None:
        ed = make_ed("distance", "within400ydsKW")
        initial_revisions = revision_count(ed)

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "distance",
            "--transform",
            "wrap-in-array",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["distance"] == ["within400ydsKW"]
        # No new revision must have been created
        assert revision_count(ed) == initial_revisions

    def test_wrap_in_array_idempotent(self) -> None:
        ed = make_ed("distance", "within400ydsKW")

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "distance",
            "--transform",
            "wrap-in-array",
            "--apply",
        )
        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["distance"] == ["within400ydsKW"]

        # Run again — should be a no-op
        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "distance",
            "--transform",
            "wrap-in-array",
            "--apply",
        )
        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["distance"] == ["within400ydsKW"]

    # ------------------------------------------------------------------
    # No revision is created
    # ------------------------------------------------------------------

    def test_apply_does_not_create_revision(self) -> None:
        ed = make_ed("count", "5")
        initial_revisions = revision_count(ed)

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "count",
            "--transform",
            "coerce-type",
            "--to-type",
            "integer",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["count"] == 5
        assert revision_count(ed) == initial_revisions

    # ------------------------------------------------------------------
    # Dry-run writes nothing
    # ------------------------------------------------------------------

    def test_dry_run_does_not_write(self) -> None:
        ed = make_ed("distance", "within400ydsKW")
        original_data = ed.data.copy()
        initial_revisions = revision_count(ed)

        # No --apply flag → dry run
        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "distance",
            "--transform",
            "wrap-in-array",
        )

        ed.refresh_from_db()
        assert ed.data == original_data
        assert revision_count(ed) == initial_revisions

    # ------------------------------------------------------------------
    # Selection scoping: event-type filter
    # ------------------------------------------------------------------

    def test_event_type_filter_restricts_to_matching_events(self) -> None:
        event_type_a = EventTypeFactory(value="type_alpha")
        event_type_b = EventTypeFactory(value="type_beta")
        event_a = EventFactory(event_type=event_type_a)
        event_b = EventFactory(event_type=event_type_b)
        ed_a = EventDetailsFactory(event=event_a, data={EVENT_DETAILS_KEY: {"flag": "yes"}})
        ed_b = EventDetailsFactory(event=event_b, data={EVENT_DETAILS_KEY: {"flag": "yes"}})
        original_b = ed_b.data.copy()

        call_command(
            "fix_event_details",
            "--event-type",
            "type_alpha",
            "--property",
            "flag",
            "--transform",
            "wrap-in-array",
            "--apply",
        )

        ed_a.refresh_from_db()
        ed_b.refresh_from_db()
        assert ed_a.data[EVENT_DETAILS_KEY]["flag"] == ["yes"]
        # ed_b is of a different event type — must not be changed
        assert ed_b.data == original_b

    # ------------------------------------------------------------------
    # Selection scoping: explicit event-id filter
    # ------------------------------------------------------------------

    def test_event_id_filter_restricts_correctly(self) -> None:
        ed_target = make_ed("note", "fix me")
        ed_other = make_ed("note", "fix me")
        original_other = ed_other.data.copy()

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed_target.event_id),
            "--property",
            "note",
            "--transform",
            "wrap-in-array",
            "--apply",
        )

        ed_target.refresh_from_db()
        ed_other.refresh_from_db()
        assert ed_target.data[EVENT_DETAILS_KEY]["note"] == ["fix me"]
        assert ed_other.data == original_other

    # ------------------------------------------------------------------
    # Refuses to run with no scope
    # ------------------------------------------------------------------

    def test_refuses_to_run_without_scope(self) -> None:
        with pytest.raises(CommandError, match="At least one of"):
            call_command(
                "fix_event_details",
                "--property",
                "note",
                "--transform",
                "wrap-in-array",
                "--apply",
            )

    # ------------------------------------------------------------------
    # Records with missing/None data are skipped safely
    # ------------------------------------------------------------------

    def test_skips_record_with_none_data_via_helper(self) -> None:
        # The DB enforces NOT NULL on EventDetails.data so we test the
        # _extract_inner_details helper directly rather than through the DB.
        cmd = Command()

        # Build a fake EventDetails-like object with data=None
        class _FakeED:
            data = None

        assert cmd._extract_inner_details(_FakeED()) is None  # type: ignore[arg-type]

    def test_skips_record_missing_event_details_key(self) -> None:
        # data present but no "event_details" outer key at all
        ed = EventDetailsFactory(data={"other_key": {"distance": "10km"}})
        original_data = ed.data.copy()

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "distance",
            "--transform",
            "wrap-in-array",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data == original_data

    def test_skips_record_missing_target_property(self) -> None:
        # event_details present but the target property is absent
        ed = EventDetailsFactory(data={EVENT_DETAILS_KEY: {"other_prop": "value"}})
        original_data = ed.data.copy()

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "nonexistent_property",
            "--transform",
            "wrap-in-array",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data == original_data

    # ------------------------------------------------------------------
    # Additional transform integration tests
    # ------------------------------------------------------------------

    def test_unwrap_single_array(self) -> None:
        ed = make_ed("status", ["active"])
        initial_revisions = revision_count(ed)

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "status",
            "--transform",
            "unwrap-single-array",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["status"] == "active"
        assert revision_count(ed) == initial_revisions

    def test_set_value_with_json_literal(self) -> None:
        ed = make_ed("count", "old_value")

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "count",
            "--transform",
            "set-value",
            "--value",
            "99",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["count"] == 99

    def test_set_value_with_raw_string_fallback(self) -> None:
        ed = make_ed("label", "old_label")

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "label",
            "--transform",
            "set-value",
            "--value",
            "new_label",
            "--apply",
        )

        ed.refresh_from_db()
        assert ed.data[EVENT_DETAILS_KEY]["label"] == "new_label"

    def test_rename_key(self) -> None:
        ed = EventDetailsFactory(data={EVENT_DETAILS_KEY: {"old_prop": "some_value", "keep": "x"}})
        initial_revisions = revision_count(ed)

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "old_prop",
            "--transform",
            "rename-key",
            "--new-property",
            "new_prop",
            "--apply",
        )

        ed.refresh_from_db()
        details = ed.data[EVENT_DETAILS_KEY]
        assert "new_prop" in details
        assert details["new_prop"] == "some_value"
        assert "old_prop" not in details
        assert details["keep"] == "x"
        assert revision_count(ed) == initial_revisions

    def test_delete_key(self) -> None:
        ed = EventDetailsFactory(data={EVENT_DETAILS_KEY: {"remove_me": "gone", "keep": "x"}})
        initial_revisions = revision_count(ed)

        call_command(
            "fix_event_details",
            "--event-id",
            str(ed.event_id),
            "--property",
            "remove_me",
            "--transform",
            "delete-key",
            "--apply",
        )

        ed.refresh_from_db()
        details = ed.data[EVENT_DETAILS_KEY]
        assert "remove_me" not in details
        assert details["keep"] == "x"
        assert revision_count(ed) == initial_revisions

    # ------------------------------------------------------------------
    # event-ids-file selection
    # ------------------------------------------------------------------

    def test_event_ids_file_selection(self, tmp_path) -> None:
        ed_target = make_ed("flag", "fix")
        ed_other = make_ed("flag", "fix")
        original_other = ed_other.data.copy()

        ids_file = tmp_path / "ids.txt"
        ids_file.write_text(f"{ed_target.event_id}\n")

        call_command(
            "fix_event_details",
            "--event-ids-file",
            str(ids_file),
            "--property",
            "flag",
            "--transform",
            "wrap-in-array",
            "--apply",
        )

        ed_target.refresh_from_db()
        ed_other.refresh_from_db()
        assert ed_target.data[EVENT_DETAILS_KEY]["flag"] == ["fix"]
        assert ed_other.data == original_other

    def test_invalid_uuid_in_event_ids_file_raises(self, tmp_path) -> None:
        ids_file = tmp_path / "bad.txt"
        ids_file.write_text("not-a-uuid\n")

        with pytest.raises(CommandError, match="Invalid UUID"):
            call_command(
                "fix_event_details",
                "--event-ids-file",
                str(ids_file),
                "--property",
                "flag",
                "--transform",
                "wrap-in-array",
            )

    # ------------------------------------------------------------------
    # Missing extra args for transforms that need them
    # ------------------------------------------------------------------

    def test_coerce_type_without_to_type_raises(self) -> None:
        ed = make_ed("count", "5")
        with pytest.raises(CommandError, match="--to-type"):
            call_command(
                "fix_event_details",
                "--event-id",
                str(ed.event_id),
                "--property",
                "count",
                "--transform",
                "coerce-type",
                "--apply",
            )

    def test_set_value_without_value_raises(self) -> None:
        ed = make_ed("label", "old")
        with pytest.raises(CommandError, match="--value"):
            call_command(
                "fix_event_details",
                "--event-id",
                str(ed.event_id),
                "--property",
                "label",
                "--transform",
                "set-value",
                "--apply",
            )

    def test_rename_key_without_new_property_raises(self) -> None:
        ed = make_ed("old_prop", "v")
        with pytest.raises(CommandError, match="--new-property"):
            call_command(
                "fix_event_details",
                "--event-id",
                str(ed.event_id),
                "--property",
                "old_prop",
                "--transform",
                "rename-key",
                "--apply",
            )
