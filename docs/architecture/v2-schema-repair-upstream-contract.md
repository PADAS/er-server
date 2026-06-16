> **Provenance.** This document is the migration-tool team's handover
> for the `repair_v2_schema` API shipped in `event-type-schema-migration-tool` v0.1.5.2
> (TestPyPI). It is mirrored here for DAS engineers'
> reference. The source of truth lives in the migration-tool team's repository.
> Updates to the upstream API should land there first; pull a refreshed copy
> into this file when the upstream changes.

---

# V2 Schema Repair Module — DAS Team Handover

> **Package:** `event-type-schema-migration-tool == 0.1.5.2` (TestPyPI)
> **Module:** `schema_migration_tool.repair`
> **Status:** Production-ready · 189 repair tests (286 total) · Executed against 13,970 real schemas: 0 crashes, 0 idempotency failures, 56 corrupted schemas repaired

---

## Installation

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            event-type-schema-migration-tool==0.1.5.2
```

(The `--extra-index-url` is needed because TestPyPI doesn't mirror dependencies — `pyjson5` comes from real PyPI.)

---

## The Problem

Schemas migrated with tool versions **≤ v0.1.3** have a bug in their `ui.fields` section: nested collection fields are stored with **un-prefixed keys** (e.g., `fields["species"]` instead of `fields["wildlife_trophies.species"]`).

This causes:
- **Cross-collection collisions**: if two collections both have a nested field called `number`, only the last one survives (last-write-wins)
- **Broken leftColumn references**: the collection's `leftColumn` array points to keys that don't exist
- **Un-editable schemas**: the UI cannot render the collection fields properly

> [!IMPORTANT]
> The `json` section is the source of truth for the repair — it is unaffected by the collection-key bug. One known exception: v0.1.3 also mis-migrated nested *checkboxes* in the json section itself; that's beyond repair's reach and needs re-migration from V1. A scan of ~100 production sites found **zero** occurrences, so this is theoretical.

---

## How It Repairs

Diagnosis is **evidence-based**: a schema is only touched when it shows a structural symptom of the bug (missing prefixed key, un-prefixed orphan parented to a collection, destroyed COLLECTION entry, un-prefixed leftColumn refs).

Rebuilt entries are sourced **harvest-then-infer**: structure comes from the JSON section, and if the mis-keyed original still survives in `ui.fields`, its UI data (`inputType`, `choices`, `placeholder`…) is recovered losslessly. Only true collision victims (original destroyed) fall back to JSON-inferred defaults.

**An existing correctly-prefixed entry is never rebuilt or overwritten.**

---

## How to Use It

### Public API

```python
from schema_migration_tool.repair import repair_v2_schema, RepairResult, RepairChange
```

### Single Schema

```python
result = repair_v2_schema(v2_schema)

if result.was_modified:
    save_to_database(result.repaired_schema)
    for change in result.changes:
        print(f"  {change.action}: {change.field_path} — {change.details}")
```

### Batch Processing (Crawler)

```python
from schema_migration_tool.repair import repair_v2_schema
from schema_migration_tool.utils.logger import LogCollector

repaired = already_correct = needs_review = 0

for schema_id, v2_schema in fetch_all_v2_schemas():
    logger = LogCollector()
    result = repair_v2_schema(v2_schema, logger=logger)

    if result.was_modified:
        repaired += 1
        save_to_database(schema_id, result.repaired_schema)
        log_changes(schema_id, result.changes)
    else:
        already_correct += 1

    # IMPORTANT: changes can be non-empty even when was_modified=False.
    # Those are diagnostics — corruption beyond the collection-key bug
    # that repair won't touch. Queue them for manual review.
    if result.changes and not result.was_modified:
        needs_review += 1
        log_changes(schema_id, result.changes)

    # Warnings flag lossy-but-correct repairs (see Operational Notes)
    if logger.get_warnings() or logger.get_errors():
        log_messages(schema_id, logger.get_logs())

print(f"Repaired: {repaired}, Correct: {already_correct}, Review: {needs_review}")
```

---

## Return Types

### `RepairResult`

| Field             | Type                 | Description                                              |
| ----------------- | -------------------- | -------------------------------------------------------- |
| `repaired_schema` | `dict`               | The fixed schema (deep copy — original is never mutated) |
| `was_modified`    | `bool`               | `True` if any changes were made                          |
| `changes`         | `list[RepairChange]` | Mutations, plus diagnostics (returned even on a no-op)   |

### `RepairChange`

| Field        | Type  | Example                                                                                                                                                                                                                                                                         |
| ------------ | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `field_path` | `str` | `"wildlife_trophies.species"`                                                                                                                                                                                                                                                   |
| `action`     | `str` | Mutations: `rebuilt_ui_entry`, `removed_stale_entry`, `fixed_left_column`, `rebuilt_collection_entry` · Diagnostics: `skipped_unknown_type`, `skipped_corrupted_json`, `skipped_invalid_property`, `skipped_invalid_name`, `survivor_type_mismatch`, `ambiguous_collision_kept` |
| `details`    | `str` | `"Re-keyed from surviving un-prefixed UI entry; Inferred TEXT/SHORT_TEXT from json type 'string'"`                                                                                                                                                                              |

---

## Guarantees

| Guarantee                            | Description                                                                                                                        |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Idempotent**                       | Already-correct schemas return `was_modified=False` with zero mutations                                                            |
| **Never overwrites healthy entries** | Existing correctly-prefixed entries are authoritative — they hold UI data JSON can't encode (e.g. LONG_TEXT) and are never rebuilt |
| **Never raises**                     | Malformed input is skipped and logged, never thrown                                                                                |
| **JSON immutable**                   | The `json` section is never modified                                                                                               |
| **Non-destructive**                  | Input dict is deep-copied, never mutated                                                                                           |
| **Matches migrator output**          | CI-enforced: repairing real v0.1.3 output reproduces a clean v0.1.4+ migration except documented unrecoverable losses              |
| **Root fields preserved**            | Deletion requires positive evidence (entry parented to a known collection); when in doubt, kept                                    |

---

## Real-World Validation

Executed against **13,970 real schemas** from ~100 production site dumps:

| Result                                             | Count                                                                   |
| -------------------------------------------------- | ----------------------------------------------------------------------- |
| Exceptions raised                                  | **0**                                                                   |
| Idempotency failures                               | **0**                                                                   |
| Corrupted production v2s found & repaired          | **56** (156 entries rebuilt, 156 orphans removed, 62 leftColumns fixed) |
| Healthy v2s incorrectly modified                   | **0**                                                                   |
| Freshly-migrated v1s where repair is a clean no-op | **13,696 / 13,696**                                                     |

Also pinned in CI against checked-in real v0.1.3 output (`python/tests/fixtures/repair_v013/`): repair reconstructs `ui` bit-for-bit when survivors exist; the only divergences are the documented unrecoverable losses below.

---

## Operational Notes (please read before the production run)

1. **Lossy rebuilds are flagged, not silent.** When a COLLECTION entry was destroyed by collision, the rebuilt container gets defaults (`buttonText='Add'`, `itemName=''`, `columns=1`) — the V1-derived originals are unrecoverable. Each one emits a warning + a `rebuilt_collection_entry` change. Spot-check these (in our sweep: a handful out of 56).
2. **Diagnostics = manual review queue.** `skipped_unknown_type`, `survivor_type_mismatch`, `ambiguous_collision_kept` mean corruption beyond the collection-key bug. Repair leaves those fields untouched rather than guessing. Our sweep saw 11 such flags across 13,970 schemas.
3. **SHORT_TEXT fallback.** A collision victim with no survivor infers `TEXT/SHORT_TEXT` even if the original was a textarea — the JSON carries no signal to distinguish them. Rare in practice (production v1s almost never declare nested textareas).

---

## Supported Field Types

| JSON Pattern                                | → V2 UI Type                                                                      |
| ------------------------------------------- | --------------------------------------------------------------------------------- |
| `string`                                    | TEXT / SHORT_TEXT                                                                 |
| `string + format: date\|time\|date-time`    | DATE_TIME                                                                         |
| `string + format: uri\|email\|uuid`         | TEXT / SHORT_TEXT                                                                 |
| `string + anyOf[$ref]`                      | CHOICE_LIST / DROPDOWN                                                            |
| `string + anyOf[oneOf]`                     | CHOICE_LIST / DROPDOWN                                                            |
| `number` or `integer`                       | NUMERIC                                                                           |
| `boolean`                                   | BOOLEAN                                                                           |
| `array + items.type: object`                | COLLECTION (recursive)                                                            |
| `array + string items + anyOf[$ref\|oneOf]` | CHOICE_LIST / LIST (multiple choice)                                              |
| `object`, `null`, anything else             | Skipped + logged (`skipped_unknown_type`) — cannot occur in correctly-migrated V2 |

---

## Questions?

The module is self-contained in `schema_migration_tool/repair/`. The test suites — `tests/unit/test_repair_v2_collection_fields.py`, `tests/unit/test_infer_ui_from_json_schema.py`, `tests/regression/test_repair_round_trip.py` (189 tests) — double as documentation of expected behavior, and `tests/fixtures/repair_v013/README.md` documents the known unrecoverable losses with real v0.1.3 artifacts.
