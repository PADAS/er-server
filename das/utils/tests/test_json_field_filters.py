"""
Unit tests for ``utils.json_field_filters.JSONFieldFilterSetMixin``.

All tests in this module are DB-free and run against mock objects only.
Tests that require a real database and model are in
``observations/tests/test_sources_filters.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rest_framework.exceptions import ValidationError

from utils.json_field_filters import (
    JSONFieldFilterSetMixin,
    _build_key_transform,
    _cast_value,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NoopParent:
    """Minimal stand-in for the FilterSet base class.

    Provides a ``filter_queryset`` that returns the queryset unchanged, so
    ``super().filter_queryset(queryset)`` inside the mixin resolves here and
    the JSON-field filter logic actually runs without needing a real FilterSet.
    """

    def filter_queryset(self, queryset: MagicMock) -> MagicMock:
        return queryset


def _make_qs() -> MagicMock:
    """Return a MagicMock queryset whose .annotate().filter() chain is introspectable."""
    qs = MagicMock()
    # Make chaining work: annotate/filter both return the same mock so multiple
    # filters can be applied sequentially.
    qs.annotate.return_value = qs
    qs.filter.return_value = qs
    return qs


def _make_mixin_instance(json_filters: dict, data: object) -> JSONFieldFilterSetMixin:
    """Construct a ``_StubFilterSet`` instance (mixin + no-op parent) with *data*.

    The real ``JSONFieldFilterSetMixin.filter_queryset`` reads ``json_field_filters``
    from ``self.__class__`` (via ``getattr(self.__class__, ...)``) and ``data``
    from ``self.data``.  Setting both here exercises the real code path without
    any patching of the method under test.
    """
    stub_cls = type(
        "_StubFilterSet",
        (JSONFieldFilterSetMixin, _NoopParent),
        {"json_field_filters": json_filters},
    )
    instance = stub_cls.__new__(stub_cls)
    instance.data = data
    return instance


# ---------------------------------------------------------------------------
# _cast_value
# ---------------------------------------------------------------------------


class TestCastValue:
    def test_string_returns_unchanged(self):
        assert _cast_value("lion", "string", "data.species") == "lion"

    def test_empty_string_is_valid(self):
        assert _cast_value("", "string", "data.species") == ""

    def test_integer_cast(self):
        assert _cast_value("42", "integer", "data.count") == 42

    def test_integer_is_not_float(self):
        result = _cast_value("10", "integer", "data.count")
        assert result == 10
        assert isinstance(result, int)

    def test_integer_invalid_raises_400(self):
        with pytest.raises(ValidationError) as exc_info:
            _cast_value("abc", "integer", "data.count")
        assert "data.count" in exc_info.value.detail

    def test_number_cast_to_float(self):
        result = _cast_value("3.14", "number", "data.weight")
        assert abs(result - 3.14) < 1e-9
        assert isinstance(result, float)

    def test_number_integer_string_accepted(self):
        assert _cast_value("5", "number", "data.weight") == 5.0

    def test_number_invalid_raises_400(self):
        with pytest.raises(ValidationError) as exc_info:
            _cast_value("not-a-float", "number", "data.weight")
        assert "data.weight" in exc_info.value.detail

    def test_boolean_true_variants(self):
        for raw in ("true", "True", "TRUE", "tRuE"):
            assert _cast_value(raw, "boolean", "data.active") is True

    def test_boolean_false_variants(self):
        for raw in ("false", "False", "FALSE"):
            assert _cast_value(raw, "boolean", "data.active") is False

    def test_boolean_extra_truthy_variants(self):
        for raw in ("1", "yes", "ok", "okay"):
            assert _cast_value(raw, "boolean", "data.active") is True

    def test_boolean_extra_falsey_variants(self):
        for raw in ("0", "no", "n"):
            assert _cast_value(raw, "boolean", "data.active") is False

    def test_boolean_invalid_raises_400(self):
        with pytest.raises(ValidationError) as exc_info:
            _cast_value("banana", "boolean", "data.active")
        assert "data.active" in exc_info.value.detail

    def test_unsupported_type_raises_400(self):
        with pytest.raises(ValidationError):
            _cast_value("x", "array", "data.tags")


# ---------------------------------------------------------------------------
# _build_key_transform
# ---------------------------------------------------------------------------


class TestBuildKeyTransform:
    def test_single_segment_string_uses_key_text_transform(self):
        from django.db.models.fields.json import KeyTextTransform

        result = _build_key_transform("additional", "species", "string")
        assert isinstance(result, KeyTextTransform)

    def test_single_segment_integer_uses_key_transform(self):
        from django.db.models.fields.json import KeyTransform

        result = _build_key_transform("additional", "count", "integer")
        assert isinstance(result, KeyTransform)
        assert not type(result).__name__ == "KeyTextTransform"

    def test_nested_path_builds_chain(self):
        from django.db.models.fields.json import KeyTextTransform

        result = _build_key_transform("additional", "horn.length", "string")
        # Outermost should be KeyTextTransform (string leaf)
        assert isinstance(result, KeyTextTransform)

    def test_nested_path_non_string_builds_key_transform_chain(self):
        from django.db.models.fields.json import KeyTransform

        result = _build_key_transform("additional", "horn.length", "integer")
        assert isinstance(result, KeyTransform)


# ---------------------------------------------------------------------------
# JSONFieldFilterSetMixin.filter_queryset (unit, no DB)
# ---------------------------------------------------------------------------

JSON_FILTERS = {
    "data": {
        "field": "additional",
        "properties": {
            "species": {"type": "string"},
            "count": {"type": "integer"},
            "active": {"type": "boolean"},
        },
    },
}


class TestJSONFieldFilterSetMixinFilterQueryset:
    """Tests for the mixin's filter_queryset override (no real DB needed)."""

    def _run(self, data: object, qs: MagicMock | None = None) -> MagicMock:
        """Run the REAL filter_queryset on the mixin with *data* and return the queryset.

        Uses ``_StubFilterSet`` (mixin + ``_NoopParent``) so the real JSON-field
        filter logic executes while ``super().filter_queryset`` is a no-op.  No
        patching of the method under test.
        """
        if qs is None:
            qs = _make_qs()
        instance = _make_mixin_instance(JSON_FILTERS, data)
        return instance.filter_queryset(qs)

    def test_no_json_filter_params_returns_queryset_unchanged(self):
        qs = _make_qs()
        self._run(data={"page": "1"}, qs=qs)
        qs.annotate.assert_not_called()

    def test_known_string_param_annotates_and_filters(self):
        qs = _make_qs()
        self._run(data={"data.species": "lion"}, qs=qs)
        qs.annotate.assert_called_once()
        qs.filter.assert_called_once()
        filter_kwargs = qs.filter.call_args[1]
        assert "_jsonfilter_data_species__exact" in filter_kwargs
        assert filter_kwargs["_jsonfilter_data_species__exact"] == "lion"

    def test_integer_param_is_cast_before_filter(self):
        qs = _make_qs()
        self._run(data={"data.count": "7"}, qs=qs)
        filter_kwargs = qs.filter.call_args[1]
        assert filter_kwargs["_jsonfilter_data_count__exact"] == 7
        assert isinstance(filter_kwargs["_jsonfilter_data_count__exact"], int)

    def test_boolean_param_is_cast_before_filter(self):
        qs = _make_qs()
        self._run(data={"data.active": "true"}, qs=qs)
        filter_kwargs = qs.filter.call_args[1]
        assert filter_kwargs["_jsonfilter_data_active__exact"] is True

    def test_unknown_data_param_is_silently_ignored(self):
        """A param like data.unknown is not in declared properties — ignored, no 400."""
        qs = _make_qs()
        self._run(data={"data.unknown": "x"}, qs=qs)
        qs.annotate.assert_not_called()
        qs.filter.assert_not_called()

    def test_injection_attempt_data_species_icontains_is_ignored(self):
        """?data.species.icontains=lion must not produce a filter (key not declared)."""
        qs = _make_qs()
        self._run(data={"data.species.icontains": "lion"}, qs=qs)
        qs.annotate.assert_not_called()
        qs.filter.assert_not_called()

    def test_last_wins_on_repeated_param(self):
        """QueryDict.get returns the last value; mixin must not add special multi-value logic."""
        from django.http import QueryDict

        qs = _make_qs()
        data = QueryDict("data.species=lion&data.species=cheetah")
        self._run(data=data, qs=qs)
        filter_kwargs = qs.filter.call_args[1]
        assert filter_kwargs["_jsonfilter_data_species__exact"] == "cheetah"

    def test_two_params_applied_independently(self):
        """Both data.species and data.count are applied as separate annotate/filter pairs."""
        qs = _make_qs()
        self._run(data={"data.species": "lion", "data.count": "3"}, qs=qs)
        assert qs.annotate.call_count == 2
        assert qs.filter.call_count == 2

    def test_invalid_cast_raises_validation_error(self):
        qs = _make_qs()
        with pytest.raises(ValidationError):
            self._run(data={"data.count": "not-an-int"}, qs=qs)

    def test_empty_config_returns_queryset_after_super(self):
        """A FilterSet with empty json_field_filters still works (no-op pass)."""
        qs = _make_qs()
        instance = _make_mixin_instance({}, {"data.species": "lion"})
        result = instance.filter_queryset(qs)
        assert result is qs
        qs.annotate.assert_not_called()

    def test_multiple_entries_on_different_columns(self):
        """Multiple entries each apply to their own column."""
        json_filters = {
            "data": {"field": "additional", "properties": {"species": {"type": "string"}}},
            "meta": {"field": "other_col", "properties": {"tag": {"type": "string"}}},
        }
        qs = _make_qs()
        instance = _make_mixin_instance(json_filters, {"data.species": "lion", "meta.tag": "tracked"})
        instance.filter_queryset(qs)
        # Two entries → two annotate/filter pairs
        assert qs.annotate.call_count == 2
        all_filter_kwargs = [c[1] for c in qs.filter.call_args_list]
        keys_used = {k for kwargs in all_filter_kwargs for k in kwargs}
        assert "_jsonfilter_data_species__exact" in keys_used
        assert "_jsonfilter_meta_tag__exact" in keys_used

    def test_nested_property_alias_in_annotation(self):
        """A declared property path ``horn.length`` → annotation alias ``_jsonfilter_data_horn_length``."""
        json_filters = {
            "data": {"field": "additional", "properties": {"horn.length": {"type": "number"}}},
        }
        qs = _make_qs()
        instance = _make_mixin_instance(json_filters, {"data.horn.length": "30"})
        instance.filter_queryset(qs)
        filter_kwargs = qs.filter.call_args[1]
        assert "_jsonfilter_data_horn_length__exact" in filter_kwargs
        assert abs(filter_kwargs["_jsonfilter_data_horn_length__exact"] - 30.0) < 1e-9
