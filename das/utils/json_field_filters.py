"""
Generic django-filter FilterSet mixin for exact-match lookups on JSON/JSONB columns.

This module is **domain-agnostic**: it contains no references to app-level models,
business vocabulary, or EarthRanger concepts.  It can be parameterised purely
via the ``json_field_filters`` class attribute on a FilterSet subclass.

It does not introduce a new concept on top of django-filter — it is just a small
helper for the one thing plain ``FilterSet`` filters can't express directly: a
query param whose name contains a dot (``data.species``), mapped onto a key
*inside* a JSON/JSONB column rather than onto a model field of its own.

Usage
-----
Declare ``json_field_filters`` on a ``FilterSet`` that also inherits this mixin::

    from utils.json_field_filters import JSONFieldFilterSetMixin
    from django_filters import rest_framework as filters

    class MyFilterSet(JSONFieldFilterSetMixin, filters.FilterSet):
        json_field_filters = {
            "data": {                            # arbitrary param prefix
                "field": "additional",          # model JSONField column
                "properties": {
                    "species": {"type": "string"},
                    "gender":  {"type": "string"},
                    "count":   {"type": "integer"},
                    "active":  {"type": "boolean"},
                },
            },
        }

        class Meta:
            model = MyModel
            fields = [...]

Just like any ordinary ``FilterSet`` filter, each entry is named by the developer
and points at a field (here, a JSON column via ``"field"``) with an exact lookup.
The top-level key (``"data"`` above) is **not** a fixed or reserved keyword — it
is simply the dict key you choose, and it becomes the query-param prefix.  Any
name works (``meta``, ``additional``, ``details``, ``attrs``, …); it is also
independent of the underlying column name in ``"field"`` (the ``"data"`` entry
above maps onto the model's ``additional`` column).

Query-parameter contract
------------------------
For an entry named ``"data"`` with property ``"species"`` the accepted query
parameter is ``data.species``.  The full param name is::

    {prefix}.{property_name}

e.g. ``?data.species=lion`` or ``?data.horn.length=30`` for a nested property
declared as ``"horn.length"``.  Had the prefix been ``"meta"`` instead, the same
property would be queried as ``?meta.species=lion``.

Only **exact** lookups are supported and structurally guaranteed:

* Filters are generated only for *declared* properties under their exact dotted
  param name.  An attempt like ``?data.species.icontains=lion`` does not match
  any declared key and is silently ignored by the normal django-filter unknown-
  param handling.
* The ORM lookup is built via ``KeyTextTransform`` / ``KeyTransform`` so that
  individual path segments are treated as data (JSONB key names), never as
  Django lookup expressions.

Mechanism used
--------------
Python class attributes cannot contain dots, so a filter for a property like
``"data.species"`` cannot be declared as a normal class-level ``Filter``
instance.  Instead, ``JSONFieldFilterSetMixin`` overrides the FilterSet's
``filter_queryset`` method.

When ``filter_queryset(queryset)`` is called by django-filter (after the normal
form validation pass has already narrowed the queryset on the *non-JSON*
declared filters), the mixin reads each ``json_field_filters`` entry from
``self.data`` (the raw ``QueryDict``), applies type casting identical to what a
``CharFilter`` / ``NumberFilter`` / ``BooleanFilter`` would do, and narrows the
queryset using ``KeyTextTransform`` / ``KeyTransform`` exact comparisons.

Behaviour details
-----------------
* **Repeated param → last-wins**: ``QueryDict.get(key)`` returns the last value
  for a repeated key.  No special multi-value handling is added.
  ``?data.species=a&data.species=b`` filters to rows where ``species == "b"``.
* **Unknown params are silently ignored**: a param like ``?data.unknown``
  whose ``unknown`` is not in the declared ``properties`` dict is simply skipped.
* **Invalid cast → 400**: a value that fails to convert to its declared type
  (e.g. ``?data.count=abc`` for ``"type": "integer"``) raises
  ``rest_framework.exceptions.ValidationError`` which django-filter's DRF
  integration surfaces as an HTTP 400.
"""

from __future__ import annotations

import logging
from typing import Any, TypeAlias

from django.db.models import QuerySet
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from rest_framework.exceptions import ValidationError

from utils.json import VALID_BOOLEAN_STRINGS, parse_bool

logger = logging.getLogger(__name__)

# Config for a single JSON-field filter entry as declared on a FilterSet subclass.
_JSONFieldFilterConfig: TypeAlias = dict[str, Any]

# Supported JSON scalar types.
_SUPPORTED_TYPES: frozenset[str] = frozenset({"string", "integer", "number", "boolean"})


def _cast_value(raw: str, declared_type: str, param_name: str) -> Any:
    """Cast *raw* (a query-param string) to the declared scalar type.

    Raises ``ValidationError`` (HTTP 400) on cast failure.  Never raises plain
    ``ValueError``.
    """
    if declared_type == "string":
        return raw
    if declared_type == "integer":
        try:
            return int(raw)
        except (ValueError, TypeError):
            raise ValidationError({param_name: f"Expected an integer value, got {raw!r}."})
    if declared_type == "number":
        try:
            return float(raw)
        except (ValueError, TypeError):
            raise ValidationError({param_name: f"Expected a numeric (float) value, got {raw!r}."})
    if declared_type == "boolean":
        if raw.lower() not in VALID_BOOLEAN_STRINGS:
            raise ValidationError(
                {param_name: f"Expected a boolean value (one of {VALID_BOOLEAN_STRINGS}), got {raw!r}."}
            )
        return parse_bool(raw)
    # Guard: caller should only pass declared types from _SUPPORTED_TYPES.
    raise ValidationError({param_name: f"Unsupported type declaration {declared_type!r} in filter spec."})


def _build_key_transform(column: str, property_path: str, declared_type: str) -> KeyTransform:
    """Return a ``KeyTransform`` expression for *property_path* inside *column*.

    Uses ``KeyTextTransform`` for ``"string"`` properties (extracts as text,
    compatible with string equality checks) and ``KeyTransform`` for numeric
    and boolean types (preserves JSON scalar types for exact matching).

    Nested property paths (e.g. ``"horn.length"``) are supported: a chain of
    ``KeyTransform`` / ``KeyTextTransform`` instances is built, one per segment.

    The outermost transform wraps the innermost, resulting in the SQL equivalent
    of ``(column->'horn'->>'length')`` for a string leaf and
    ``(column->'horn'->'length')`` for a non-string leaf.
    """
    segments = property_path.split(".")
    use_text = declared_type == "string"

    # Build innermost → outermost chain.
    # For a single segment: just one Transform applied to the column name.
    # For multiple: each inner segment uses KeyTransform (preserves JSON type),
    # and the outermost uses KeyTextTransform or KeyTransform according to leaf type.
    if len(segments) == 1:
        transform_cls = KeyTextTransform if use_text else KeyTransform
        return transform_cls(segments[0], column)

    # Multiple segments: traverse with KeyTransform for all intermediate nodes;
    # apply the correct transform at the leaf.
    source: str | KeyTransform = column
    for seg in segments[:-1]:
        source = KeyTransform(seg, source)  # type: ignore[arg-type]  # str is a valid field source

    leaf_cls = KeyTextTransform if use_text else KeyTransform
    return leaf_cls(segments[-1], source)  # type: ignore[arg-type]


class JSONFieldFilterSetMixin:
    """Mixin for ``django_filters.FilterSet`` subclasses that adds exact-only
    filtering on declared JSON/JSONB column properties via ``{prefix}.{prop}``
    query params.

    Declare ``json_field_filters`` as a class attribute::

        json_field_filters = {
            "data": {
                "field": "additional",
                "properties": {
                    "species": {"type": "string"},
                    "gender":  {"type": "string"},
                },
            },
        }

    The mixin overrides ``filter_queryset`` to apply these filters *after* the
    standard django-filter declared-field pass.  All params are taken from
    ``self.data``.
    """

    # Subclasses override this.
    json_field_filters: dict[str, _JSONFieldFilterConfig] = {}

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        # Run the standard declared-filter pass first.
        queryset = super().filter_queryset(queryset)  # type: ignore[misc]

        json_filters: dict[str, _JSONFieldFilterConfig] = getattr(self.__class__, "json_field_filters", {})
        if not json_filters:
            return queryset

        # ``self.data`` is the raw QueryDict (or dict-like) passed to the FilterSet.
        data = getattr(self, "data", {})

        for prefix, config in json_filters.items():
            column: str = config["field"]
            properties: dict[str, dict[str, str]] = config.get("properties", {})

            param_prefix = f"{prefix}."

            for prop_path, prop_spec in properties.items():
                param_name = f"{param_prefix}{prop_path}"
                # QueryDict.get() returns the *last* value for a repeated key.
                # Unknown params (not in properties) are skipped automatically
                # because we only iterate declared property keys.
                raw_value = data.get(param_name)
                if raw_value is None:
                    continue

                declared_type = prop_spec.get("type", "string")
                casted = _cast_value(raw_value, declared_type, param_name)

                transform = _build_key_transform(column, prop_path, declared_type)

                # Annotate with a deterministic alias and filter on it.  The alias
                # bridges the dotted param name onto a dot-free ORM identifier by
                # replacing dots with underscores.
                alias = f"_jsonfilter_{prefix}_{prop_path.replace('.', '_')}"
                queryset = queryset.annotate(**{alias: transform}).filter(**{f"{alias}__exact": casted})

        return queryset
