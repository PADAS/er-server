from __future__ import annotations

import pytest

from schemas.format_serializers import (
    ENUM_EXTRA_KEY,
    OUTPUT_FORMAT_ENUM,
    OUTPUT_FORMAT_ONE_OF,
    apply_output_format,
    get_output_format_override,
    output_format_override,
    serialize_enum_fragment,
    serialize_one_of_fragment,
)


class TestFormatSerializersEmptyOptions:
    """Empty mapped_items must emit spec-valid JSON Schema (no empty enum/oneOf)."""

    def test_serialize_enum_fragment_empty_drops_enum_key(self) -> None:
        schema: dict = {}
        serialize_enum_fragment(schema, [])
        assert "enum" not in schema

    def test_serialize_enum_fragment_empty_keeps_x_enum_extra_as_empty_dict(self) -> None:
        schema: dict = {}
        serialize_enum_fragment(schema, [])
        assert schema[ENUM_EXTRA_KEY] == {}

    def test_serialize_enum_fragment_empty_adds_not_nothing_validates(self) -> None:
        schema: dict = {}
        serialize_enum_fragment(schema, [])
        assert schema["not"] == {}

    def test_serialize_one_of_fragment_empty_emits_false_subschema(self) -> None:
        schema: dict = {}
        serialize_one_of_fragment(schema, [])
        assert schema["oneOf"] == [False]

    def test_serialize_enum_fragment_non_empty_unchanged(self) -> None:
        """Non-empty path must still emit enum + x-enumExtra (no regression)."""
        schema: dict = {}
        serialize_enum_fragment(schema, [{"value": "a", "label": "A"}])
        assert schema["enum"] == ["a"]
        assert schema[ENUM_EXTRA_KEY] == {"a": {"display": "A"}}
        assert "not" not in schema

    def test_serialize_one_of_fragment_non_empty_unchanged(self) -> None:
        """Non-empty path must still emit a list of branch objects (no regression)."""
        schema: dict = {}
        serialize_one_of_fragment(schema, [{"value": "a", "label": "A"}])
        assert schema["oneOf"] == [{"const": "a", "title": "A"}]
        assert schema["oneOf"] != [False]


class TestFormatSerializers:
    def test_serialize_enum_fragment_preserves_row_order_and_duplicate_values(self) -> None:
        """Non-unique values: every row appears in ``enum``; ``x-enumExtra`` keys last row's metadata."""
        mapped_items = [
            {"value": "a", "label": "First", "description": "d1"},
            {"value": "a", "label": "Second", "description": "d2"},
        ]
        schema: dict = {}
        serialize_enum_fragment(schema, mapped_items)
        assert schema["enum"] == ["a", "a"]
        assert schema[ENUM_EXTRA_KEY]["a"]["display"] == "Second"
        assert schema[ENUM_EXTRA_KEY]["a"]["description"] == "d2"

    def test_serialize_one_of_includes_x_prefixed_extras(self) -> None:
        mapped_items = [{"value": 1, "label": "One", "icon": "i1"}]
        schema: dict = {}
        serialize_one_of_fragment(schema, mapped_items)
        assert schema["oneOf"][0] == {"const": 1, "title": "One", "x-icon": "i1"}

    def test_enum_fragment_uses_value_as_extra_key(self) -> None:
        """``x-enumExtra`` keys are the same objects as ``enum`` values (no stringification)."""
        schema: dict = {}
        serialize_enum_fragment(
            schema,
            [
                {"value": 1, "label": "Int one"},
                {"value": "1", "label": "Str one"},
            ],
        )
        assert schema["enum"] == [1, "1"]
        assert schema[ENUM_EXTRA_KEY] == {1: {"display": "Int one"}, "1": {"display": "Str one"}}

    def test_apply_output_format_enum(self) -> None:
        schema: dict = {"type": "string"}
        apply_output_format(schema, [{"value": "x", "label": "X"}], OUTPUT_FORMAT_ENUM)
        assert schema["enum"] == ["x"]
        assert schema[ENUM_EXTRA_KEY]["x"]["display"] == "X"

    def test_apply_output_format_one_of(self) -> None:
        schema: dict = {"type": "string"}
        apply_output_format(schema, [{"value": "x", "label": "X"}], OUTPUT_FORMAT_ONE_OF)
        assert schema["oneOf"][0]["const"] == "x"
        assert "enum" not in schema


class TestOutputFormatOverride:
    def test_no_override_by_default(self) -> None:
        assert get_output_format_override() is None

    def test_override_visible_inside_context_and_restored_on_exit(self) -> None:
        with output_format_override(OUTPUT_FORMAT_ONE_OF):
            assert get_output_format_override() == OUTPUT_FORMAT_ONE_OF
        assert get_output_format_override() is None

    def test_nested_overrides_stack_and_restore(self) -> None:
        with output_format_override(OUTPUT_FORMAT_ENUM):
            with output_format_override(OUTPUT_FORMAT_ONE_OF):
                assert get_output_format_override() == OUTPUT_FORMAT_ONE_OF
            assert get_output_format_override() == OUTPUT_FORMAT_ENUM
        assert get_output_format_override() is None

    def test_override_restored_after_exception(self) -> None:
        with pytest.raises(RuntimeError):
            with output_format_override(OUTPUT_FORMAT_ONE_OF):
                raise RuntimeError("boom")
        assert get_output_format_override() is None

    def test_rejects_unknown_format(self) -> None:
        with pytest.raises(ValueError, match="Unsupported output_format"):
            with output_format_override("bogus"):
                pass
