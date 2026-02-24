# Event Type Sync

Recommendations for synchronizing event types for offline use. Aimed at mobile clients that want to minimize downloads and the number of checks to detect changes.

## Version 1 Event Type Sync

### Recommended: One list, one ETag

Use the event types list API as the single source for both the event type catalog and (optionally) schemas. The response **ETag** reflects any change to the list or to any event type’s metadata and rendered schema (including choice lists). Use it to avoid re-downloading when nothing has changed.

**Endpoint**

```
GET /api/v1.0/activity/events/eventtypes
```

**Query parameters**

| Parameter         | Description |
|-------------------|-------------|
| `include_schema`  | If `true`, each event type in the list includes its rendered JSON schema (with choices). Prefer this for offline sync so one request gives list + schemas. |
| `include_inactive`| Include inactive event types. |
| `updated_since`   | ISO date/time. Return only event types whose `updated_at` is on or after this time. Use for incremental sync. **Note:** Only event type record updates are reflected; changes to choice lists referenced in schemas do **not** change `updated_at`, so `updated_since` alone does not signal choice-list changes. Rely on the list ETag for that. |

**Optimizing “do I need to download?”**

1. **Store the ETag** from the last successful list response (header `ETag`).
2. On the next sync, send a **conditional request**: same URL with header `If-None-Match: <stored-etag>`.
3. If the server responds **304 Not Modified**, nothing changed — skip downloading the body and keep your cached event types.
4. If the server responds **200 OK**, replace your cache with the new response and store the new `ETag`.

This minimizes both checks (one conditional GET) and downloads (no body when unchanged).

**Optimizing full and incremental downloads**

- **Initial / full sync:** Call the list with `include_schema=true` (and `include_inactive` if needed). You get all event types and their schemas in one response; one ETag covers the whole set.
- **Incremental sync:** Call the list with `updated_since=<last_sync_iso>`. You get only event types that changed (by `updated_at`). If you need to be sure choice lists are up to date, still do a conditional GET on the full list (with `If-None-Match`) periodically or when you suspect schema/choice changes; use 304 to avoid re-downloading when unchanged.

**Example list response (with `include_schema=false`)**

```json
{
  "data": [
    {
      "id": "6c90e5f5-ae8e-4e7f-a8dd-26e5d2909a74",
      "has_events_assigned": true,
      "icon": "accident_rep",
      "value": "accident_rep",
      "display": "Accident",
      "ordernum": 1,
      "is_collection": false,
      "category": {
        "id": "007a45d3-2aba-4ed1-b3fc-e09fc0ad41f8",
        "value": "security",
        "display": "Security",
        "is_active": true,
        "ordernum": 1,
        "flag": "user",
        "permissions": [
          "read",
          "create",
          "delete",
          "update"
        ]
      },
      "icon_id": "accident_rep",
      "is_active": true,
      "default_priority": 300,
      "default_state": "new",
      "geometry_type": "Point",
      "resolve_time": null,
      "auto_resolve": false,
      "url": "https://easterisland.pamdas.org/api/v1.0/activity/events/eventtypes/6c90e5f5-ae8e-4e7f-a8dd-26e5d2909a74"
    }
  ]
}
```

### Single event type (no schema)

```
GET /api/v1.0/activity/events/eventtypes/<eventtype_id>
```

Supports conditional GET (ETag). Does **not** support `include_schema`; use the list with `include_schema=true` or the schema endpoints below if you need schemas.

### Per–event-type schema (no ETag)

```
GET /api/v1.0/activity/events/schema/eventtype/<eventtype_value>
```

Returns the full schema for one event type (by `value`). There is **no ETag** on this endpoint; prefer the list with `include_schema=true` for offline sync so a single ETag covers all types and schemas.

### General event schema (not detailed per-type schemas)

```
GET /api/v1.0/activity/events/schema?format=json
```

Returns a **general** event schema — not the detailed, per-event-type schemas. Mobile developers typically call this endpoint to get the **`reported_by`** list, which is optionally collected for all event types. Use it when you need that shared list; for full per-type form definitions use the event types list with `include_schema=true` or the per-type schema endpoint. This endpoint has an **ETag**.

**Example general schema (fragment)**

```json
{
  "data": {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
      "id": {
        "type": "string",
        "required": false,
        "title": "Id"
      },
      "location": {
        "type": "string",
        "required": false,
        "title": "Location"
      }
    }
  }
}
```

## Summary for mobile clients

| Goal | Recommendation |
|------|----------------|
| Fewest “has anything changed?” checks | Conditional GET on `GET .../events/eventtypes` with `If-None-Match`; treat 304 as “no download needed”. |
| Fewest full downloads | Use the list ETag as above; only download when you get 200. |
| One-shot full sync | `GET .../events/eventtypes?include_schema=true` (and `include_inactive` if needed). |
| Incremental sync by time | `GET .../events/eventtypes?updated_since=<iso>`; remember `updated_since` does not reflect choice-list changes — use the list ETag when you need to detect those. |
| Where to get schemas | **Detailed per-type schemas:** list with `include_schema=true` or per-type `.../events/schema/eventtype/<value>`. **General schema / `reported_by` list:** `.../events/schema?format=json`. |

---

## Version 2 Event Type Sync

The v2 API exposes event types (version 2 only) under a different base path and with a resource keyed by **event type value** (slug) rather than UUID. Use it when your app targets v2 event types for offline sync.

**V2 ETags do not include rendered schemas or choices.** Both the list and single-event-type ETags are computed from metadata only (e.g. event type and category `updated_at`, or model fields). They do **not** include a hash of the rendered schema or choice lists. So if only choice-list data changes, the ETag may stay the same and a conditional GET can return 304 even though the response body (with `include_schema=true`) would have changed. When you must be sure choice lists are up to date, re-download periodically or after other cues instead of relying solely on 304.

### Recommended: List with conditional GET

Use the v2 event types list as the main source for the catalog and, optionally, schemas. The response **ETag** is computed from event type and category `updated_at` values (metadata only; see above). Use **If-None-Match** to avoid re-downloading when the list is unchanged.

**Endpoint**

```
GET /api/v2.0/activity/eventtypes
```

**Query parameters**

| Parameter         | Description |
|-------------------|-------------|
| `include_schema`  | If `true`, each event type in the list includes its **raw** schema (as stored). This is **not** a rendered schema: choice lists and `$ref` are not expanded. For rendered schemas (with choices), use the schema endpoints with `pre_render=true` (see below). |
| `include_inactive`| Include inactive event types (default is active only). |
| `updated_since`   | ISO date/time. Return only event types whose `updated_at` is on or after this time. Use for incremental sync. **Note:** As in v1, only event type record updates are reflected; choice-list changes do not update `updated_at`. |
| `category`        | Filter by category value(s). |
| `is_collection`   | Filter by `is_collection` (true/false). |

**Optimizing “do I need to download?”**

1. **Store the ETag** from the last successful list response.
2. On the next sync, send **If-None-Match: &lt;stored-etag&gt;** with the same URL (and same query params).
3. **304 Not Modified** → nothing changed; keep your cache.
4. **200 OK** → replace your cache and store the new ETag.

**Optimizing full and incremental downloads**

- **Initial / full sync:** Call the list with `include_schema=true` (and `include_inactive` if needed).
- **Incremental sync:** Use `updated_since=<last_sync_iso>`. For certainty about schema/choice changes, rely on the list ETag and conditional GET.

**Note:** The v2 list ETag is based on `updated_at` and category `updated_at` only (see the V2 ETag note at the start of this section). Conditional GET still minimizes full downloads when metadata or list membership change.

### Single event type (detail)

```
GET /api/v2.0/activity/eventtypes/<eventtype_value>
```

Use **event type value** (slug), e.g. `accident_rep`. UUID is also accepted for compatibility. Supports **conditional GET** (ETag). Use query param **`include_schema=true`** to include the event type’s **raw** schema in the response (not rendered; no choice expansion). The detail ETag is based on the event type’s model fields only — it does **not** include the rendered schema or choices, so 304 can be returned even when only choice lists have changed.

### List all schemas

```
GET /api/v2.0/activity/eventtypes/schemas
```

Returns a list of schemas for all v2 event types (one entry per type, with success/failure and optional errors). Query param **`pre_render=true`** returns **rendered** schemas (choices expanded, refs resolved); without it, schemas are **raw**. To get rendered schemas with choice lists, you must use this endpoint (or the single schema endpoint below) with **`pre_render=true`** — the list/detail `include_schema` option does not render. There is **no ETag** on this endpoint; for sync, prefer the list with `include_schema=true` and conditional GET.

### Single event type schema

```
GET /api/v2.0/activity/eventtypes/<eventtype_value>/schema
```

Returns the schema for one event type. **`pre_render=true`** returns the rendered schema. There is **no ETag** on this endpoint.

### Event type updates (revision history)

```
GET /api/v2.0/activity/eventtypes/<eventtype_value>/updates
```

Returns the revision history for the event type (paginated). Use when you need to show or sync change history; not required for basic offline catalog + schema sync.

## Summary for mobile clients (v2)

| Goal | Recommendation |
|------|----------------|
| Fewest “has anything changed?” checks | Conditional GET on `GET .../eventtypes` with `If-None-Match`. Remember v2 ETags do not include rendered schema/choices. |
| One-shot full sync | `GET .../eventtypes?include_schema=true` (and `include_inactive` if needed). |
| Incremental sync by time | `GET .../eventtypes?updated_since=<iso>`. |
| Where to get schemas | **Raw schema** (in list/detail): `include_schema=true`. **Rendered schema** (choices expanded): `.../eventtypes/schemas?pre_render=true` or `.../eventtypes/<value>/schema?pre_render=true`. List + conditional GET is best for minimizing requests when raw schema is enough. |
| Ensuring choice lists are current | V2 ETags are metadata-only; re-download when you need to guarantee schema/choice changes are reflected. |
