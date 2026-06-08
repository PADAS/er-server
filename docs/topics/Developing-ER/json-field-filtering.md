# JSON-field filtering on list endpoints — design & rationale

How list endpoints (e.g. `SourcesView`, later `SubjectsView`) expose exact-match
filtering over keys inside a JSON/JSONB column (`additional`) via
`utils.json_field_filters.JSONFieldFilterSetMixin`, and **why** the design is the
way it is.

> Scope: this documents the **exact-match** iteration. Operator grammar
> (`gt`/`lt`/`in`/range/`contains`) is deliberately deferred; see
> [Future: typed operators](#future-typed-operators).

## The shape

A `FilterSet` declares a `json_field_filters` class attribute:

```python
class SourceFilterSet(JSONFieldFilterSetMixin, filters.FilterSet):
    json_field_filters = {
        "additional": {              # query-param prefix → e.g. ?additional.species=lion
            "field": "additional",   # the model JSONB column
            "open": True,            # allow ANY additional.<key>, not just declared ones
            "properties": {          # OPTIONAL — documentation / forward metadata, NOT a typecast
                "species": {"type": "string"},
                "gender":  {"type": "string"},
            },
        },
    }
```

A request like `?additional.species=lion&additional.habitat=savanna` filters
`Source` rows to those whose `additional` JSONB has `species == "lion"` **and**
`habitat == "savanna"`.

## Decisions and why

### 1. Exact match uses text extraction (`->>` / `KeyTextTransform`), not typed comparison

PostgreSQL's `->>` operator extracts any scalar JSON value as **text**: a JSON
number `5` becomes `"5"`, `true` becomes `"true"`, strings pass through. So a
single text comparison matches strings, numbers, and booleans uniformly —
`?additional.age=5` matches a row storing `{"age": 5}` (JSON number) *and* one
storing `{"age": "5"}` (JSON string).

**Benefit:** we never need to know a key's type to filter it exactly. One code
path covers every scalar, which is what makes filtering on *arbitrary
user-defined keys* possible at all (see decision 3).

### 2. We dropped value type-casting (no `_cast_value`, no typed `KeyTransform` leaf)

The earlier design cast the query string to a declared type and used a typed
`KeyTransform` comparison for non-string keys. We removed that. Three reasons:

- **No performance benefit.** There are **no indexes** on any `additional`
  column anywhere in the codebase (verified), so every `additional.*` filter is
  a sequential scan regardless of typing. And even with an index, the
  `->>'k'='v'` / `->'k'=v` equality form is **not GIN-indexable** — a jsonb GIN
  index only accelerates containment (`@>`) and existence (`?`) operators. The
  only thing that accelerates the equality form is a *per-key btree expression
  index* (`((additional->>'k'))`), and the conventional, well-trodden form to
  index is the **text** extraction. So text is, if anything, *more*
  index-friendly than typed — never less.
- **Typing user data is a recall liability.** `additional` is
  user/tenant-populated and **not type-guaranteed**: the same key is commonly
  stored as `5` in some rows and `"5"` in others. A typed filter silently
  **misses half** of them; text extraction matches both — which is almost always
  the intended behaviour for user-facing filtering.
- **Fewer failure modes.** With text comparison there is no cast to fail, so the
  request-time `ValidationError`/400 path disappears entirely.

### 3. Openness is per-field config (`open: True`), and "open" is *safer* than the old whitelist

`open=False` (default) — only keys declared under `properties` are filterable;
anything else is ignored. Use this for JSON fields with a fixed, known shape.

`open=True` — **any** `{prefix}.<key>` present in the query is filtered. Use this
for genuinely open, user-defined bags like `additional`.

Counter-intuitively, opening the field **reduces** the most dangerous footgun.
The old whitelist *silently skipped* an undeclared key, so a filter the caller
believed was applied did nothing → the endpoint returned the **unfiltered** set
(a silent over-broad result). Under `open=True`:

- a real key filters correctly;
- a typo'd / non-existent key extracts `NULL` for every row → **zero matches**
  (an empty result), which is a *visible* signal, not "everything".

The only thing given up is authoring-time key validation (a typo'd key becomes
"empty result" instead of "rejected"). For live queries that is an acceptable —
arguably better — trade.

### 4. `properties` + `type` are kept as documentation and forward metadata

Exact match ignores the declared types (decision 1), but we keep the
declarations because:

- they document the **known/common** keys for a field (and can drive OpenAPI);
- the **future operator grammar genuinely needs types** — `->>` compares
  lexically, so `additional.age > "9"` would wrongly rank `"10" < "9"`. Numeric
  and date *ordering* operators must use real typed comparison. Keeping the type
  metadata now means the operator PR doesn't have to re-derive the known-key set.

### 5. Injection safety — why there is no "reserved lookup" blocklist

Path segments are passed as **data** to `KeyTransform` / `KeyTextTransform`
constructors, never interpolated into a Django lookup string. The result is
annotated under a generated alias and filtered via `<alias>__exact`. So a key
like `additional.species.icontains` is treated as a (here, impossible) nested
JSON path `species → icontains`, not as an `icontains` ORM lookup — it simply
yields zero matches. This is why, unlike a `additional__<key>=` approach, no
blocklist of reserved lookup names (`has_key`, `contains`, `isnull`, …) is
needed: the lookup grammar is never exposed to user input.

Annotation aliases are generated from a **per-request counter**
(`_jsonfilter_0`, `_jsonfilter_1`, …), never derived from the raw key, so
arbitrary key names (hyphens, spaces, unicode, or two keys that would collide
after sanitisation) cannot produce an invalid identifier or an alias clash.

### 6. Configuration is validated at class-definition time

`__init_subclass__` validates each `json_field_filters` entry when the
`FilterSet` class is defined, raising `ImproperlyConfigured` for a missing /
non-string `field`, a non-bool `open`, a non-dict `properties`, or a declared
`type` outside `{string, integer, number, boolean}`. Misconfiguration fails at
import, not at the first request. (Open-mode keys are request-time and therefore
not class-validatable — the alias-safety handling in decision 5 covers them.)

## Repeated params → last-wins

`QueryDict.get()` returns the last value for a repeated key, so
`?additional.species=lion&additional.species=cheetah` filters on `cheetah`. This
matches how an ordinary django-filter exact field behaves; no special
multi-value handling is added.

## Rollout / scope

- **Live queries now.** `SourceFilterSet.additional` is `open=True` on this
  branch (ERA-13310). `SubjectsView`/`SubjectFilterSet` get the same treatment
  on its branch.
- **The dynamic-schema `$ref` path is transparent.** `DynamicSchemaFromSourceView`
  forwards request query params verbatim to the source view; it adds no
  filtering of its own, so opening the FilterSet opens it for `$ref`-resolved
  choice lists too — at *query* time.
- **The metaschema `$ref` allowlist stays closed (for now).** That allowlist is a
  *save-time* gate on event-type schemas; it does not run at query time. It only
  needs to open to a wildcard `additional.*` if/when authors must **save**
  `$ref`s containing arbitrary additional keys. That is a separate change on the
  metaschema branch and is intentionally out of scope here.

## Future: typed operators

When the operator grammar lands (`field=op:value`), ordering operators
(`gt`/`lt`/range) and date handling will use the `properties` type declarations
to build *typed* comparisons for the declared keys, while exact match stays
text-based. If query performance ever becomes a problem on a hot, known key, the
optimisation path is a GIN index plus an `@>` containment rewrite (which is
type-sensitive) — decoupled from this work and premature today.
