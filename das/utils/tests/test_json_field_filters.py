"""
Unit tests for ``utils.json_field_filters.JSONFieldFilterSetMixin``.

All tests in this module are DB-free and run against mock objects only.
Tests that require a real database and model are in
``observations/tests/test_sources_filters.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from django.core.exceptions import ImproperlyConfigured

from utils.json_field_filters import JSONFieldFilterSetMixin, _build_key_transform

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

    Note: ``type(...)`` triggers ``__init_subclass__``, so ``json_filters`` must be
    structurally valid (or the call itself raises ``ImproperlyConfigured``).
    """
    stub_cls = type(
        "_StubFilterSet",
        (JSONFieldFilterSetMixin, _NoopParent),
        {"json_field_filters": json_filters},
    )
    instance = stub_cls.__new__(stub_cls)
    instance.data = data
    return instance


def _filter_values(qs: MagicMock) -> list:
    """Return a flat list of all filter-kwarg *values* passed across all .filter() calls."""
    result = []
    for c in qs.filter.call_args_list:
        result.extend(c[1].values())
    return result


# ---------------------------------------------------------------------------
# _build_key_transform
# ---------------------------------------------------------------------------


class TestBuildKeyTransform:
    def test_single_segment_uses_key_text_transform(self):
        from django.db.models.fields.json import KeyTextTransform

        result = _build_key_transform("additional", "species")
        assert isinstance(result, KeyTextTransform)

    def test_single_segment_always_text_regardless_of_name(self):
        """Even a key named 'count' or 'active' uses KeyTextTransform (type-agnostic)."""
        from django.db.models.fields.json import KeyTextTransform

        assert isinstance(_build_key_transform("additional", "count"), KeyTextTransform)
        assert isinstance(_build_key_transform("additional", "active"), KeyTextTransform)

    def test_nested_path_leaf_is_key_text_transform(self):
        from django.db.models.fields.json import KeyTextTransform

        result = _build_key_transform("additional", "horn.length")
        assert isinstance(result, KeyTextTransform)

    def test_nested_path_intermediate_uses_key_transform(self):
        """Intermediate segments use plain KeyTransform to navigate JSONB sub-objects."""
        from django.db.models.fields.json import KeyTextTransform, KeyTransform

        result = _build_key_transform("additional", "horn.length")
        # Leaf is KeyTextTransform; its source should be a KeyTransform (the 'horn' node).
        assert isinstance(result, KeyTextTransform)
        # The source is the intermediate KeyTransform wrapping the column.
        assert isinstance(result.lhs, KeyTransform)

    def test_deeply_nested_path_leaf_is_key_text_transform(self):
        from django.db.models.fields.json import KeyTextTransform

        result = _build_key_transform("col", "a.b.c")
        assert isinstance(result, KeyTextTransform)


# ---------------------------------------------------------------------------
# JSONFieldFilterSetMixin.filter_queryset — closed mode (open=False, default)
# ---------------------------------------------------------------------------

JSON_FILTERS_CLOSED = {
    "data": {
        "field": "additional",
        "properties": {
            "species": {"type": "string"},
            "count": {"type": "integer"},
            "active": {"type": "boolean"},
        },
    },
}


class TestJSONFieldFilterSetMixinClosedMode:
    """Tests for filter_queryset when open=False (the default)."""

    def _run(self, data: object, qs: MagicMock | None = None) -> MagicMock:
        if qs is None:
            qs = _make_qs()
        instance = _make_mixin_instance(JSON_FILTERS_CLOSED, data)
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
        # Value is compared as raw text (no cast).
        assert "lion" in _filter_values(qs)

    def test_known_integer_key_is_compared_as_text(self):
        """Closed mode: declared key 'count' is extracted and compared as text (no int cast)."""
        qs = _make_qs()
        self._run(data={"data.count": "7"}, qs=qs)
        qs.annotate.assert_called_once()
        # Value is passed as-is (string), not cast to int.
        assert "7" in _filter_values(qs)

    def test_known_boolean_key_is_compared_as_text(self):
        """Closed mode: declared key 'active' is extracted and compared as text (no bool cast)."""
        qs = _make_qs()
        self._run(data={"data.active": "true"}, qs=qs)
        assert "true" in _filter_values(qs)

    def test_undeclared_param_is_silently_ignored(self):
        """A param like data.unknown is not in declared properties — ignored, no filter."""
        qs = _make_qs()
        self._run(data={"data.unknown": "x"}, qs=qs)
        qs.annotate.assert_not_called()
        qs.filter.assert_not_called()

    def test_injection_attempt_data_species_icontains_is_ignored(self):
        """?data.species.icontains=lion is not a declared key — silently ignored."""
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
        assert "cheetah" in _filter_values(qs)
        assert "lion" not in _filter_values(qs)

    def test_two_params_applied_independently(self):
        """Both data.species and data.count are applied as separate annotate/filter pairs."""
        qs = _make_qs()
        self._run(data={"data.species": "lion", "data.count": "3"}, qs=qs)
        assert qs.annotate.call_count == 2
        assert qs.filter.call_count == 2

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
        values = _filter_values(qs)
        assert "lion" in values
        assert "tracked" in values

    def test_nested_property_path_applies_filter(self):
        """A declared property path 'horn.length' is applied correctly."""
        json_filters = {
            "data": {"field": "additional", "properties": {"horn.length": {"type": "number"}}},
        }
        qs = _make_qs()
        instance = _make_mixin_instance(json_filters, {"data.horn.length": "30"})
        instance.filter_queryset(qs)
        # Value is passed as raw text (no float cast).
        assert "30" in _filter_values(qs)

    def test_alias_is_counter_based_not_derived_from_input(self):
        """Aliases are counter-based (_jsonfilter_N), not derived from user input."""
        qs = _make_qs()
        self._run(data={"data.species": "lion"}, qs=qs)
        filter_kwargs = qs.filter.call_args[1]
        # Exactly one key; its name should follow the counter pattern.
        assert len(filter_kwargs) == 1
        alias_key = next(iter(filter_kwargs))
        assert alias_key.startswith("_jsonfilter_")
        # Must NOT contain the raw field name (counter-only).
        assert "species" not in alias_key
        assert "__exact" in alias_key


# ---------------------------------------------------------------------------
# JSONFieldFilterSetMixin.filter_queryset — open mode (open=True)
# ---------------------------------------------------------------------------

JSON_FILTERS_OPEN = {
    "additional": {
        "field": "additional",
        "open": True,
        "properties": {
            "species": {"type": "string"},
            "gender": {"type": "string"},
        },
    },
}


class TestJSONFieldFilterSetMixinOpenMode:
    """Tests for filter_queryset when open=True."""

    def _run(self, data: object, qs: MagicMock | None = None) -> MagicMock:
        if qs is None:
            qs = _make_qs()
        instance = _make_mixin_instance(JSON_FILTERS_OPEN, data)
        return instance.filter_queryset(qs)

    def test_declared_key_is_applied_via_text_extraction(self):
        """A declared key ('species') is applied even in open mode."""
        qs = _make_qs()
        self._run(data={"additional.species": "lion"}, qs=qs)
        qs.annotate.assert_called_once()
        assert "lion" in _filter_values(qs)

    def test_arbitrary_undeclared_key_is_applied(self):
        """An undeclared key ('anykey') is applied when open=True."""
        qs = _make_qs()
        self._run(data={"additional.anykey": "somevalue"}, qs=qs)
        qs.annotate.assert_called_once()
        assert "somevalue" in _filter_values(qs)

    def test_numeric_json_value_matched_by_text_representation(self):
        """A JSON int stored as 5 is matched by the text '5' (type-agnostic)."""
        qs = _make_qs()
        self._run(data={"additional.age": "5"}, qs=qs)
        assert "5" in _filter_values(qs)

    def test_nested_path_in_open_mode(self):
        """An arbitrary nested path like 'horn.length' is applied in open mode."""
        qs = _make_qs()
        self._run(data={"additional.horn.length": "30"}, qs=qs)
        qs.annotate.assert_called_once()
        assert "30" in _filter_values(qs)

    def test_key_with_non_identifier_chars_does_not_crash(self):
        """A key like 'foo-bar' (hyphen) is safe in open mode (alias is counter-based)."""
        qs = _make_qs()
        # Should not raise; alias is derived from counter, not from the raw key.
        self._run(data={"additional.foo-bar": "baz"}, qs=qs)
        qs.annotate.assert_called_once()
        assert "baz" in _filter_values(qs)
        # The alias key in filter kwargs must be a valid Python identifier.
        filter_kwargs = qs.filter.call_args[1]
        alias_key = next(iter(filter_kwargs))
        # The alias (stripped of the __exact suffix) must be a valid Python identifier —
        # counter-based, no raw user-input chars.
        assert alias_key.removesuffix("__exact").isidentifier()
        assert "foo-bar" not in alias_key

    def test_malformed_path_empty_remainder_is_skipped(self):
        """'additional.' (empty remainder) is skipped — not applied."""
        qs = _make_qs()
        self._run(data={"additional.": "x"}, qs=qs)
        qs.annotate.assert_not_called()

    def test_malformed_path_double_dot_is_skipped(self):
        """'additional..x' (consecutive dots / empty segment) is skipped."""
        qs = _make_qs()
        self._run(data={"additional..x": "val"}, qs=qs)
        qs.annotate.assert_not_called()

    def test_no_params_no_filters(self):
        qs = _make_qs()
        self._run(data={}, qs=qs)
        qs.annotate.assert_not_called()

    def test_multiple_open_keys_each_produce_a_filter(self):
        """Two arbitrary keys → two separate annotate/filter pairs."""
        qs = _make_qs()
        self._run(data={"additional.foo": "1", "additional.bar": "2"}, qs=qs)
        assert qs.annotate.call_count == 2
        assert qs.filter.call_count == 2
        values = _filter_values(qs)
        assert "1" in values
        assert "2" in values

    def test_aliases_are_unique_per_filter(self):
        """Each applied filter gets a distinct alias (counter increments)."""
        qs = _make_qs()
        self._run(data={"additional.foo": "1", "additional.bar": "2"}, qs=qs)
        all_aliases = []
        for c in qs.filter.call_args_list:
            all_aliases.extend(c[1].keys())
        assert len(all_aliases) == len(set(all_aliases)), "Aliases must be unique across all filters"


# ---------------------------------------------------------------------------
# Class-time validation (__init_subclass__)
# ---------------------------------------------------------------------------


class TestImproperlyConfiguredValidation:
    """Tests that malformed json_field_filters raises ImproperlyConfigured at class creation."""

    def _make_bad_cls(self, json_filters: dict) -> None:
        """Attempt to define a subclass with *json_filters*; expect ImproperlyConfigured."""
        type("_BadFilterSet", (JSONFieldFilterSetMixin, _NoopParent), {"json_field_filters": json_filters})

    def test_missing_field_raises(self):
        with pytest.raises(ImproperlyConfigured, match="'field'"):
            self._make_bad_cls({"data": {"properties": {}}})

    def test_non_string_field_raises(self):
        with pytest.raises(ImproperlyConfigured, match="'field'"):
            self._make_bad_cls({"data": {"field": 123}})

    def test_empty_string_field_raises(self):
        with pytest.raises(ImproperlyConfigured, match="'field'"):
            self._make_bad_cls({"data": {"field": ""}})

    def test_open_not_bool_raises(self):
        with pytest.raises(ImproperlyConfigured, match="'open'"):
            self._make_bad_cls({"data": {"field": "col", "open": "yes"}})

    def test_properties_not_dict_raises(self):
        with pytest.raises(ImproperlyConfigured, match="'properties'"):
            self._make_bad_cls({"data": {"field": "col", "properties": ["species"]}})

    def test_declared_property_unknown_type_raises(self):
        with pytest.raises(ImproperlyConfigured, match="'type'"):
            self._make_bad_cls({"data": {"field": "col", "properties": {"name": {"type": "array"}}}})

    def test_valid_config_does_not_raise(self):
        """A well-formed config must not raise."""
        self._make_bad_cls(
            {
                "additional": {
                    "field": "additional",
                    "open": True,
                    "properties": {
                        "species": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                }
            }
        )

    def test_properties_omitted_is_valid(self):
        """'properties' is optional; omitting it is valid."""
        self._make_bad_cls({"data": {"field": "additional", "open": True}})

    def test_open_omitted_is_valid(self):
        """'open' defaults to False; omitting it is valid."""
        self._make_bad_cls({"data": {"field": "additional", "properties": {"x": {"type": "string"}}}})

    def test_property_spec_string_raises_improperly_configured_not_attribute_error(self):
        """A property spec that is a plain string (not a dict) must raise ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="spec must be a dict"):
            self._make_bad_cls({"additional": {"field": "additional", "properties": {"sex": "string"}}})

    def test_property_spec_list_raises_improperly_configured_not_attribute_error(self):
        """A property spec that is a list (not a dict) must raise ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="spec must be a dict"):
            self._make_bad_cls({"additional": {"field": "additional", "properties": {"sex": []}}})
