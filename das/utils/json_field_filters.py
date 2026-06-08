"""
Generic django-filter FilterSet mixin for exact-match lookups on JSON/JSONB columns.

This module is **domain-agnostic**: it contains no references to app-level models,
business vocabulary, or EarthRanger concepts.  It can be parameterised purely
via the ``json_field_filters`` class attribute on a FilterSet subclass.

It does not introduce a new concept on top of django-filter — it is just a small
helper for the one thing plain ``FilterSet`` filters can't express directly: a
query param whose name contains a dot (``additional.species``), mapped onto a key
*inside* a JSON/JSONB column rather than onto a model field of its own.

Usage
-----
Declare ``json_field_filters`` on a ``FilterSet`` that also inherits this mixin::

    from utils.json_field_filters import JSONFieldFilterSetMixin
    from django_filters import rest_framework as filters

    class MyFilterSet(JSONFieldFilterSetMixin, filters.FilterSet):
        json_field_filters = {
            "additional": {           # arbitrary param prefix (also the query-param prefix)
                "field": "additional", # model JSONField column
                "open": True,          # allow filtering ANY additional.<key>
                "properties": {        # optional: documents known keys; forward metadata for
                    "species": {"type": "string"},   # future typed-operator PR
                    "gender":  {"type": "string"},
                },
            },
        }

        class Meta:
            model = MyModel
            fields = [...]

The top-level key (``"additional"`` above) is **not** a fixed or reserved keyword —
it is simply the dict key you choose, and it becomes the query-param prefix.  Any
name works (``meta``, ``data``, ``attrs``, …); it is also independent of the
underlying column name in ``"field"``.

Query-parameter contract
------------------------
For an entry named ``"additional"`` with ``open=True``, **any** query parameter of
the form ``additional.<key>`` is accepted and applied as a text-extraction exact
match on the JSONB column.

For ``open=False`` (the default, *closed mode*), only keys declared in ``properties``
are applied; all other ``{prefix}.*`` params are silently ignored (not an error).

Examples::

    ?additional.species=lion          # single key
    ?additional.horn.length=30        # nested path (two levels)

Exact-match semantics (text extraction, type-agnostic)
-------------------------------------------------------
All comparisons use Postgres's ``->>`` text-extraction operator via
``KeyTextTransform``.  Because the extracted value is always text, the filter
value is compared as-is (the raw query-string).  This means:

* A number stored as JSON ``5`` is matched by ``?prefix.age=5``.
* A boolean stored as JSON ``true`` is matched by ``?prefix.flag=true``.
* No type casting is attempted — there is no 400 path for "wrong type".

Type-agnostic text extraction was chosen deliberately: ``additional`` is a
user/tenant-populated JSONB bag with open-ended keys and no schema enforcement.
A key stored as a JSON integer in some rows and as a JSON string in others is
matched consistently by the text representation in both cases.

``properties`` declarations
---------------------------
``properties`` is **optional** and has no effect on the exact-match logic.  It is
kept as:

1. Human documentation of well-known keys for a given entry.
2. Forward-looking metadata for a future typed-operator PR (numeric/date ordering,
   range queries) where real types will be required.

Behaviour details
-----------------
* **open=True / open=False**: when ``True``, any ``{prefix}.<key>`` param in the
  request data is applied.  When ``False`` (default), only ``properties`` keys are
  applied.
* **Repeated param → last-wins**: ``QueryDict.get(key)`` returns the last value
  for a repeated key.  No special multi-value handling is added.
  ``?additional.species=a&additional.species=b`` filters to rows where
  ``species == "b"`` (text).
* **Nonexistent / typo'd key → zero matches (open mode)**: when ``open=True`` and
  a supplied key does not exist in any row's JSON, the text extraction returns
  ``NULL``, which never matches the non-NULL query string.  The result is an empty
  (or zero-matching) queryset.  The key is NOT silently skipped.
* **Unknown params silently ignored (closed mode)**: when ``open=False``, a param
  like ``?prefix.unknown`` is simply not in the declared ``properties`` dict and is
  skipped without error.
* **Injection safety**: path segments (from both declared ``properties`` keys and
  open-mode request keys) are passed as *data arguments* to
  ``KeyTransform``/``KeyTextTransform``, never interpolated into a lookup string.
  Django passes them as bind parameters to the DB driver, so arbitrary JSONB key
  names cannot alter the query structure.  No reserved-lookup blocklist is needed.

Class-time validation
---------------------
``JSONFieldFilterSetMixin`` validates each entry in ``json_field_filters`` at
**class definition time** (via ``__init_subclass__``) and raises
``django.core.exceptions.ImproperlyConfigured`` for:

* Missing or non-string ``field``.
* ``open`` present and not a ``bool``.
* ``properties`` present and not a ``dict``.
* A declared property spec whose ``type`` (if given) is not one of
  ``{"string", "integer", "number", "boolean"}``.

Open-mode request keys cannot be validated at class time (they are supplied at
request time) — the alias-safety and injection-safety handling covers those.
"""

from __future__ import annotations

import itertools
from typing import Any, TypeAlias

from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from django.db.models.fields.json import KeyTextTransform, KeyTransform

# Config for a single JSON-field filter entry as declared on a FilterSet subclass.
_JSONFieldFilterConfig: TypeAlias = dict[str, Any]

# Supported JSON scalar types — kept for class-time validation of declared
# property specs (forward metadata for the future typed-operator PR).
_SUPPORTED_TYPES: frozenset[str] = frozenset({"string", "integer", "number", "boolean"})


def _build_key_transform(column: str, property_path: str) -> KeyTextTransform:
    """Return a ``KeyTextTransform`` expression for *property_path* inside *column*.

    Always uses text extraction (``->>``) at the leaf so that comparisons are
    type-agnostic: JSON integers, booleans, and strings all round-trip to their
    text representations and can be compared with a plain string equality check.

    Nested property paths (e.g. ``"horn.length"``) are supported: intermediate
    segments use ``KeyTransform`` (preserving the JSONB sub-object) and the
    final segment uses ``KeyTextTransform`` (extracting as text).

    All path segments are passed as *data* to the transform constructors, never
    interpolated into a lookup string — so arbitrary user-supplied key names are
    injection-safe regardless of their content.
    """
    segments = property_path.split(".")

    if len(segments) == 1:
        return KeyTextTransform(segments[0], column)

    # Multiple segments: traverse intermediate nodes with KeyTransform (preserves
    # JSONB sub-object), then extract the leaf as text.
    source: str | KeyTransform = column
    for seg in segments[:-1]:
        source = KeyTransform(seg, source)  # type: ignore[arg-type]  # str is valid as field source

    return KeyTextTransform(segments[-1], source)  # type: ignore[arg-type]


def _validate_json_field_filters(cls_name: str, json_field_filters: dict[str, _JSONFieldFilterConfig]) -> None:
    """Validate *json_field_filters* at class-definition time.

    Raises ``ImproperlyConfigured`` on any structural problem so that
    misconfigured FilterSet subclasses fail loudly at import time rather than
    silently producing wrong query behaviour at request time.
    """
    for prefix, config in json_field_filters.items():
        loc = f"{cls_name}.json_field_filters[{prefix!r}]"

        field = config.get("field")
        if not isinstance(field, str) or not field:
            raise ImproperlyConfigured(f"{loc}: 'field' must be a non-empty string, got {field!r}.")

        open_flag = config.get("open", False)
        if not isinstance(open_flag, bool):
            raise ImproperlyConfigured(f"{loc}: 'open' must be a bool, got {open_flag!r}.")

        properties = config.get("properties")
        if properties is not None:
            if not isinstance(properties, dict):
                raise ImproperlyConfigured(f"{loc}: 'properties' must be a dict, got {type(properties).__name__!r}.")
            for prop_name, prop_spec in properties.items():
                if not isinstance(prop_spec, dict):
                    raise ImproperlyConfigured(
                        f"{loc}.properties[{prop_name!r}]: spec must be a dict, got {type(prop_spec).__name__!r}."
                    )
                declared_type = prop_spec.get("type")
                if declared_type is not None and declared_type not in _SUPPORTED_TYPES:
                    raise ImproperlyConfigured(
                        f"{loc}.properties[{prop_name!r}]: 'type' must be one of {sorted(_SUPPORTED_TYPES)}, "
                        f"got {declared_type!r}."
                    )


class JSONFieldFilterSetMixin:
    """Mixin for ``django_filters.FilterSet`` subclasses that adds exact-only
    filtering on JSON/JSONB column properties via ``{prefix}.{prop}`` query params.

    See the module docstring for full semantics, the ``open`` flag, and the
    ``properties`` metadata contract.

    Declare ``json_field_filters`` as a class attribute::

        json_field_filters = {
            "additional": {
                "field": "additional",
                "open": True,
                "properties": {
                    "species": {"type": "string"},
                    "gender":  {"type": "string"},
                },
            },
        }
    """

    # Subclasses override this.
    json_field_filters: dict[str, _JSONFieldFilterConfig] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        jff = cls.__dict__.get("json_field_filters")
        if jff is not None:
            _validate_json_field_filters(cls.__name__, jff)

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        # Run the standard declared-filter pass first.
        queryset = super().filter_queryset(queryset)  # type: ignore[misc]

        json_filters: dict[str, _JSONFieldFilterConfig] = getattr(self.__class__, "json_field_filters", {})
        if not json_filters:
            return queryset

        # ``self.data`` is the raw QueryDict (or dict-like) passed to the FilterSet.
        data = getattr(self, "data", {})

        # Counter for collision-free, identifier-safe annotation aliases.
        # We do NOT derive the alias from raw user input because open-mode keys
        # can contain non-identifier characters (hyphens, spaces, unicode, etc.)
        # and two different keys could collide after sanitisation.
        alias_counter = itertools.count()

        for prefix, config in json_filters.items():
            column: str = config["field"]
            open_mode: bool = config.get("open", False)
            properties: dict[str, dict[str, str]] = config.get("properties", {})

            param_prefix = f"{prefix}."

            if open_mode:
                # Scan ALL keys in self.data that start with "{prefix}.".
                # The remainder after the prefix dot is the dotted path.
                paths_to_apply: list[str] = []
                for key in data.keys():
                    if not key.startswith(param_prefix):
                        continue
                    remainder = key[len(param_prefix) :]
                    # Skip empty/malformed remainders: empty string, leading/trailing
                    # dot, consecutive dots (empty segment anywhere).
                    if not remainder or ".." in remainder or remainder.startswith(".") or remainder.endswith("."):
                        continue
                    paths_to_apply.append(remainder)
            else:
                # Closed mode: only apply declared properties.
                paths_to_apply = list(properties.keys())

            for prop_path in paths_to_apply:
                param_name = f"{param_prefix}{prop_path}"
                # QueryDict.get() returns the *last* value for a repeated key.
                raw_value = data.get(param_name)
                if raw_value is None:
                    continue

                transform = _build_key_transform(column, prop_path)

                # Use a counter-based alias to avoid collisions on arbitrary
                # user-supplied key names (open mode).  The alias is never derived
                # from raw user input.
                alias = f"_jsonfilter_{next(alias_counter)}"
                queryset = queryset.annotate(**{alias: transform}).filter(**{f"{alias}__exact": raw_value})

        return queryset
