# EventType V2: SMART DM/CDM Feature Analysis

## Overview

This document analyzes the features found in SMART's Data Model (DM) and Configurable Data Model (CDM) architecture compared to EarthRanger's EventType V2 system. The goal is to identify feature gaps and recommend how ER could support equivalent capabilities within its JSON Schema-based approach.

**References:**
- SMART DM Architecture: `~/projects/smart/smart-dm-architecture.md`
- SMART Patrol Architecture: `~/projects/smart/smart-patrol.md`
- ER EventType V2: `docs/architecture/eventtype_v2.md`

---

## Feature Comparison

### 1. Hierarchical Data Model vs. Flat Event Types

**SMART** uses a hierarchical category tree. Categories form a deep tree (`Human Activity > People > direct observation`) with attributes attached at any level and shareable across branches. The tree drives queries via hkey range scans (e.g., `WHERE cat_hkey >= 'wildlife.' AND cat_hkey < 'wildlife/'` matches all wildlife subcategories).

**ER V2** is a flat, single-level schema. Each event type defines its own `properties` object with no parent/child category structure.

**Gap**: ER has no concept of a shared category taxonomy. Each event type is self-contained. To support SMART-like workflows, ER would need either:
- A category tree model that event types reference (similar to how SMART's DM categories work)
- Or a way to compose event types hierarchically (an event type that inherits fields from a parent)

---

### 2. Shared/Reusable Attributes vs. Per-EventType Fields

**SMART** attributes are first-class Conservation Area-level entities with a many-to-many mapping to categories. The same `species` attribute can appear on "Wildlife", "Carcass", and "Bushmeat" categories -- change it once, it updates everywhere. An ancestor-descendant blocking rule keeps queries unambiguous.

**ER V2** fields are defined inline per event type. Choice lists can be shared via `$ref` URLs to a choices API, but the field definitions themselves (title, description, constraints, UI config) are duplicated across event types. There is no concept of a field pool.

**Gap**: ER lacks a reusable attribute registry. Adding a "species" field to 10 event types means 10 independent field definitions. This creates drift risk and makes bulk updates (e.g., renaming "Species" to "Species Observed") require touching every event type.

---

### 3. TREE-Type Attributes (Hierarchical Values)

**SMART** supports TREE-type attributes where the value space itself is hierarchical (e.g., full taxonomic tree: `CHORDATA > MAMMALIA > CARNIVORA > Felidae > Panthera > Panthera leo`). This enables:
- Drill-down queries using hkey range scans
- Aggregation at any taxonomic level
- Species list imports from standard databases (e.g., IUCN)
- Flattening the tree to a searchable list on mobile via the `FLATTEN_TREE` CDM option

**ER V2** choice fields are flat lists (`anyOf` with `const`/`title` pairs). There is no nested or hierarchical value selection.

**Gap**: This is a significant feature gap. Conservation use cases frequently need taxonomic selection and the ability to query/aggregate at different levels of a hierarchy (e.g., "all Felidae observations" vs. "Panthera leo specifically"). ER would need a hierarchical choice/tree field type.

---

### 4. Configurable Data Model (CDM) -- Collection Profiles

**SMART's** CDM is a presentation layer overlay on the master data model. It controls:
- Which categories/attributes are visible on mobile
- Field-level options: required, enter-once, flatten-tree, multiselect
- Per-context subsetting (a "Law Enforcement" CDM shows different categories than a "Wildlife Patrol" CDM)
- Active value filtering (show only 50 locally-relevant species out of thousands)
- CDM-level settings: instant GPS, photo-first workflow, icon set, EarthRanger integration toggle

Multiple CDMs can coexist for one Conservation Area, each deployed as a separate mobile project.

**ER V2's** `ui` section serves a similar purpose (field types, input types, sections, layout) but it is tightly coupled to the event type. There is no separation between "what data exists" and "how to collect it in this context." Every event type has exactly one UI definition.

**Gap**: ER has no equivalent of the CDM overlay pattern. You cannot take the same underlying schema and present it differently for different collection contexts (e.g., a simplified view for community rangers vs. a full view for researchers). This would require decoupling the data schema from collection profiles.

---

### 5. Attribute Configuration per Context

**SMART's** CDM allows per-node attribute options: the same `species` attribute can be visible in one CDM node but hidden in another, required in one context but optional in another. The active value list can be filtered per CDM (show only locally-relevant species).

Key CDM per-attribute options:
| Option | Description |
|--------|-------------|
| `IS_VISIBLE` | Whether the attribute appears in mobile UI |
| `FLATTEN_TREE` | Flattens a TREE attribute to a searchable list |
| `ENTER_ONCE` | Value entered once and applied to all observations in a patrol leg |
| `MULTISELECT` | Allow multiple selections for LIST attributes |
| `IS_REQUIRED` | Field must be filled before saving |

**ER V2** has no equivalent. A field's required/optional status and choice options are global to the event type.

**Gap**: Context-dependent field configuration. This matters when the same event type needs different collection experiences for different teams or regions.

---

### 6. Multi-Source Observation Model

**SMART's** waypoint/observation architecture supports multiple data sources (PATROL, SURVEY, ASSET, SMARTCOLLECT) feeding into the same observation model with the same DM categories. The source is a discriminator on the waypoint table. Data collected through any CDM maps back to DM UUIDs, so queries and reports work uniformly regardless of collection source.

**ER** events are tied to event types but are already source-agnostic in a similar way (events can come from sensors, mobile, or manual entry).

**Comparable**: Both systems handle multi-source data, though SMART's patrol/survey/asset distinction is more formalized with dedicated bridge tables and metadata per source type.

---

### 7. Field Type Comparison

| Feature | SMART DM | ER V2 |
|---------|----------|-------|
| Numeric | Yes (with aggregation functions: avg, max, min, sum, stddev, variance) | Yes (min/max/multipleOf) |
| Text | Yes | Yes (short/long) |
| Single-select list | Yes (LIST) | Yes (choice with anyOf) |
| Multi-select list | Yes (MLIST) | Yes (array + uniqueItems) |
| Hierarchical tree | **Yes (TREE)** | **No** |
| Boolean | Yes | No (could use enum with two values) |
| Date | Yes | Yes (format: date) |
| Location/geometry | No (on waypoint, not attribute) | Yes (Point, Polygon fields) |
| Attachments | Yes (on waypoint) | Yes (array of objects) |
| Collections/nested | No | Yes (COLLECTION type) |
| Aggregation functions | Yes (configurable per numeric attribute) | No |

---

### 8. What ER V2 Has That SMART Lacks

- **JSON Schema standards compliance**: SMART uses custom XML; ER uses JSON Schema 2020-12 with standard tooling and validators
- **Nested object collections**: ER's COLLECTION field type allows repeatable groups of fields (e.g., multiple animal sightings within one event)
- **Inline geometry fields**: ER can have location fields within the event data itself, not just on the container
- **Modern UI definition system**: Responsive layouts with sections and columns
- **Static validation**: ER schemas can be validated without a database or runtime; SMART requires the Java application layer
- **Reference resolution**: Standard `$ref` mechanism vs. SMART's custom XML cross-references

---

## Recommendations

### Priority 1: Hierarchical Choice/Tree Field Type

Add a `TREE` field type that supports hierarchical value selection with path-based keys. This enables taxonomic selection, drill-down querying, and aggregation at any level.

**Approach options:**
- A recursive `anyOf` structure in JSON Schema with nested groups
- A `$ref` to a tree-structured choices endpoint that returns hierarchical data
- A dedicated tree value model at the tenant level (closer to SMART's `dm_attribute_tree` table)

The tree should support:
- Selection at any level (leaf or branch)
- hkey-style paths for range queries
- Optional flattening to a searchable list on mobile
- Import from standard taxonomies (e.g., IUCN species lists)

---

### Priority 2: Shared Attribute Registry

Create a first-class attribute definition model at the tenant level, separate from event types. Event types would reference shared attributes by ID rather than defining fields inline.

**Key design decisions:**
- Attributes belong to the tenant (like SMART's CA-level attributes), not to any specific event type
- The mapping between event types and attributes is many-to-many
- Changes to a shared attribute propagate to all event types that reference it
- Consider whether to enforce SMART's ancestor-descendant blocking rule (likely unnecessary without a category hierarchy)

This could be implemented as an extension of the existing choices `$ref` system -- expanding it from just choice values to full field definitions.

---

### Priority 3: Collection Profiles (CDM Equivalent)

Decouple the UI/collection configuration from the event type schema. Allow multiple "collection profiles" per event type that control:
- Field visibility (which fields to show)
- Required status overrides (required in one profile, optional in another)
- Active value subsetting (show only relevant choices from a large list)
- Layout and section organization
- Mobile-specific options (enter-once, photo-first)

**Approach**: The existing `ui` section of V2 event types could become the default profile, with additional named profiles stored alongside it. Each profile references the same `json` schema but provides its own UI configuration.

```json
{
  "json": { /* shared data schema */ },
  "ui": { /* default profile */ },
  "profiles": {
    "law-enforcement": { /* override visibility, required, layout */ },
    "community-ranger": { /* simplified field set */ }
  }
}
```

---

### Priority 4: Category Taxonomy

Consider whether ER needs a category hierarchy above event types. SMART's tree structure enables powerful cross-cutting queries ("all Human Activity observations") that ER's flat event type model doesn't naturally support.

ER's existing event type categories may partially address this, but they are not as deep or query-integrated as SMART's hkey-based system. Options:
- Extend event type categories to support nesting (tree structure)
- Add hkey-style paths for range-based querying
- Allow event types to belong to multiple categories (like SMART's attribute sharing)

---

### Lower Priority

| Feature | Description | SMART Equivalent |
|---------|-------------|------------------|
| Enter-once fields | Value persists across observations in a session | CDM `ENTER_ONCE` option |
| Active value subsetting | Show only relevant choices from a large list per context | CDM `attributeConfig` |
| Name source tracking | Track whether display names come from the master model or were overridden | CDM `source="DM"` vs `source="CM"` |
| Aggregation functions | Per-numeric-field configurable aggregations | DM `dm_aggregation` + `dm_att_agg_map` |
| Boolean field type | Native true/false toggle | DM BOOLEAN attribute type |

---

## Architectural Decision: Hierarchy vs. Composition

The biggest architectural decision is whether to add hierarchy to ER's data model (SMART's approach) or to achieve similar functionality through composition and references within the existing flat JSON Schema paradigm.

**SMART's hierarchical approach:**
- Enables powerful hkey range queries for cross-cutting analysis
- Natural fit for taxonomic and categorical data
- Well-proven in conservation domain (15+ years)
- Tightly coupled -- changes to the tree structure affect queries, CDMs, and mobile packages

**ER's composition approach (extend V2):**
- Aligned with JSON Schema standards and tooling ecosystem
- More flexible for non-hierarchical use cases
- Easier to validate statically
- May not support the full depth of SMART's query and reporting capabilities without additional infrastructure

A hybrid approach is likely best: keep ER V2's JSON Schema foundation but add targeted hierarchical features (tree field type, category nesting, shared attributes) where the conservation domain demands them.
