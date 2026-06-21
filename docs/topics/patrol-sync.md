# Patrol Sync

Recommendations for synchronizing patrol-related data for offline use. Aimed at mobile clients that want to minimize downloads and the number of checks to detect changes.

This guide covers **patrol types** (the catalog of types, like "Foot", "Vehicle"), the **tracked-by schema** (who can be reported as segment leader), and **patrols** and **patrol segments** (the actual patrol instances and their segments). Only patrol types and the tracked-by schema support conditional GET (ETag / Last-Modified); patrol and segment list/detail do not.

**Note:** The web UI currently supports only **one patrol segment per patrol**. The API allows multiple segments per patrol, but clients that aim for parity with the web UI should treat one segment per patrol as the supported case.

---

## Patrol Types (catalog for offline)

Patrol types define the kinds of patrols (e.g. Foot, Vehicle). Sync the list for offline so the app can create patrols and show type metadata (display name, icon, priority, etc.).

### Recommended: List with conditional GET

Use the patrol types list as the single source for the catalog. The response **ETag** and **Last-Modified** reflect any change to the list (metadata only: `value`, `display`, `ordernum`, `icon_id`, `is_active`, `default_priority`, `updated_at`, `image_url`). Use **If-None-Match** and optionally **If-Modified-Since** to avoid re-downloading when nothing has changed.

**Endpoint**

```
GET /api/v1.0/activity/patrols/types
```

**Query parameters**

There are no query parameters for the list; it returns all patrol types the user is allowed to see.

**Optimizing "do I need to download?"**

1. **Store the ETag** (and optionally **Last-Modified**) from the last successful list response.
2. On the next sync, send a **conditional request** with the same URL and:
   - **If-None-Match:** your stored ETag value
   - Optionally **If-Modified-Since:** your stored Last-Modified value (RFC 7232 format).
3. If the server responds **304 Not Modified**, nothing changed — skip downloading the body and keep your cached patrol types.
4. If the server responds **200 OK**, replace your cache with the new response and store the new **ETag** and **Last-Modified**.

This minimizes both checks (one conditional GET) and downloads (no body when unchanged).

**Optimizing full download**

- **Initial / full sync:** Call the list once; there is no `include_schema` or `updated_since` for patrol types — the list is small and metadata-only. One request is enough.

### Single patrol type (detail)

```
GET /api/v1.0/activity/patrols/types/<patrol_type_id>
```

Use the patrol type **UUID**. Supports **conditional GET** (ETag and Last-Modified). Use when you need to refresh or check a single type; for full catalog sync, the list endpoint with conditional GET is simpler.

### Patrol type response fields

| Field              | Writable | Description |
|--------------------|----------|-------------|
| `id`               | No       | UUID primary key. |
| `value`            | Yes      | Unique string identifier for this type (e.g. `"foot"`). |
| `display`          | Yes      | Human-readable label. |
| `ordernum`         | Yes      | Sort order hint. Nullable. |
| `icon`             | Yes      | Raw stored icon identifier. Empty string when no explicit icon has been set. |
| `icon_id`          | No       | Resolved icon identifier. Equals `icon` when an icon is stored; falls back to `value` when `icon` is empty and a static marker image exists for that value, otherwise `"generic_rep"`. **Use `icon_id` for display** — it handles the fallback. Write `icon` when setting or clearing an icon. |
| `default_priority` | Yes      | Default priority for patrols of this type. |
| `is_active`        | Yes      | Whether this type is available for new patrols. |

### Patrol type write endpoints

| Method   | URL                                       | Description       |
|----------|-------------------------------------------|-------------------|
| `POST`   | `/api/v1.0/activity/patrols/types`        | Create a patrol type. |
| `PUT`    | `/api/v1.0/activity/patrols/types/<id>`   | Replace a patrol type. |
| `PATCH`  | `/api/v1.0/activity/patrols/types/<id>`   | Partially update a patrol type. |
| `DELETE` | `/api/v1.0/activity/patrols/types/<id>`   | Delete a patrol type. |

`value` must be unique per tenant. Attempting to create a duplicate returns **400 Bad Request**. Required permissions: `add_patroltype`, `change_patroltype`, or `delete_patroltype` respectively.

---

## Tracked-by schema (segment leaders / "reported by")

When creating or editing patrol segments, clients often need the list of subjects (and optionally users) that can be selected as segment leader ("tracked by"). This is provided by the tracked-by schema endpoint. It has an **ETag** so you can avoid re-downloading when the set of possible leaders has not changed.

**Endpoint**

```
GET /api/v1.0/activity/patrols/trackedby
```

Returns metadata describing the schema for "tracked by" (e.g. subject list). The **ETag** is derived from the set of subjects available to the user. Use **If-None-Match** for conditional GET; **304 Not Modified** means the schema/options are unchanged.

**Optimizing "do I need to download?"**

1. Store the **ETag** from the last successful response.
2. On the next sync, send **If-None-Match:** your stored ETag value.
3. **304** — keep your cached schema; **200** — replace cache and store the new ETag.

---

## Patrols (list and detail)

Patrols are the actual patrol instances (with one or more segments). The list and detail endpoints **do not** support ETag or Last-Modified. Use query parameters to limit results and paginate; for incremental-style sync you can use the **filter** with a **date_range** to fetch patrols overlapping a time window.

**Endpoints**

```
GET /api/v1.0/activity/patrols
GET /api/v1.0/activity/patrols/<patrol_id>
```

**List query parameters**

| Parameter               | Description |
|-------------------------|-------------|
| `filter`                | JSON object for advanced filtering. Example: `{"date_range":{"lower":"2020-09-16T00:00:00.000Z"}, "text":"search text"}`. Use **date_range** with `lower`/`upper` (ISO date/time) to restrict by patrol time; supports incremental-style sync by requesting patrols overlapping a given window. |
| `exclude_empty_patrols` | If `true`, exclude patrols that have no patrol segments. Default is `false`. |
| `status`                | Filter by state(s). Allowed values depend on `StateFilters` (e.g. scheduled, active, done, overdue). Can be repeated. |

Responses are **paginated**. There is **no ETag** on the list or detail; you cannot use conditional GET to skip re-downloading. To minimize data transfer, use **filter** (e.g. `date_range`) and pagination, and store the last sync time or last requested range for incremental pulls.

**Single patrol**

Detail returns one patrol by **UUID**. No ETag; refetch when you need the latest state.

### Patrol request payloads (POST, PATCH, PUT)

**Create patrol:** `POST /api/v1.0/activity/patrols`

**Update patrol:** `PATCH` or `PUT /api/v1.0/activity/patrols/<patrol_id>`

Request body (JSON). All fields are optional on create; omit fields you are not changing on update.

| Field             | Type     | Description |
|-------------------|----------|-------------|
| `objective`       | string   | Patrol objective (text). Can be blank/null. |
| `priority`        | integer  | Priority. Allowed values: `0` (Gray), `100` (Green), `200` (Amber), `300` (Red). Default is `0`. |
| `state`           | string   | Patrol state: `"open"`, `"done"`, or `"cancelled"`. Default is `"open"`. |
| `title`           | string   | Patrol title. Max 255 characters. Can be blank/null. |
| `notes`           | array    | List of note objects. Each note: `{ "text": "..." }`. Optional `id` for updates (to update an existing note). |
| `patrol_segments`| array    | List of segment objects (see **Patrol segment request payloads** below). When creating a patrol you can include segments in this array; do not send `patrol` inside each segment (server sets it). Include `id` in a segment to update an existing segment. |

Validation: `scheduled_start` must be earlier than `scheduled_end` in any segment. Patrol state may be auto-set to `"done"` when all segments have ended.

---

## Patrol segments (list and detail)

Patrol segments are the legs of a patrol (each has a type, time range, leader, etc.). The **web UI supports only one segment per patrol**; the API may return or accept multiple segments per patrol, but the web UI does not. List and detail **do not** support ETag or Last-Modified.

**Endpoints**

```
GET  /api/v1.0/activity/patrols/segments
GET  /api/v1.0/activity/patrols/segments/<segment_id>
```

List is **paginated**. Use when syncing segment data; no conditional GET is available.

**Segment–events**

```
GET /api/v1.0/activity/patrols/segments/<patrol_segment_id>/events
```

Returns events linked to a patrol segment. No ETag.

### Patrol segment request payloads (POST, PATCH, PUT)

Segments can be created or updated in two ways: **nested in a patrol** (in `patrol_segments` when posting to `POST /patrols` or `PATCH/PUT /patrols/<id>`) or **standalone** via the segments list.

**Create segment (standalone):** `POST /api/v1.0/activity/patrols/segments`

**Update segment (standalone):** `PATCH` or `PUT /api/v1.0/activity/patrols/segments/<segment_id>`

When nested in a patrol payload, omit `patrol` (the server sets it). When posting to the segments endpoint, **`patrol` is required** (patrol UUID).

| Field             | Type   | Required (standalone) | Description |
|-------------------|--------|------------------------|-------------|
| `patrol`          | UUID   | Yes (standalone only)  | Patrol ID. Omit when segment is nested in a patrol body. |
| `patrol_type`     | string | No                     | Patrol type `value` (e.g. `"foot"`, `"vehicle"`). From patrol types catalog. |
| `leader`          | object | No                     | Segment leader (who is tracked). Object: `{ "content_type": "<model>", "id": "<uuid>" }`. Allowed `content_type`: `"observations.subject"`, `"accounts.user"`, `"activity.community"`. Use the tracked-by schema to get valid options. Can be `null`. |
| `scheduled_start` | string | No                     | ISO 8601 date/time. Scheduled start. |
| `scheduled_end`   | string | No                     | ISO 8601 date/time. Scheduled end. Must be after `scheduled_start` if both are set. |
| `time_range`      | object | No                     | Actual patrol time. `{ "start_time": "<iso>", "end_time": "<iso>" }`. Both nullable. `start_time` must be earlier than `end_time` if both set. |
| `start_location`  | object | No                     | Start point. `{ "latitude": <number>, "longitude": <number> }`. |
| `end_location`    | object | No                     | End point. Same shape as `start_location`. |
| `id`              | UUID   | No                     | Include when updating an existing segment (nested or standalone). |

Read-only in responses (do not send when creating/updating): `image_url`, `icon_id`, `events`.

---

## Patrol sub-resources (notes, files)

Patrol notes and files are nested under a patrol:

```
GET /api/v1.0/activity/patrols/<patrol_id>/notes
GET /api/v1.0/activity/patrols/<patrol_id>/notes/<note_id>
GET /api/v1.0/activity/patrols/<patrol_id>/files
GET /api/v1.0/activity/patrols/<patrol_id>/files/...
```

These endpoints do not expose ETag or Last-Modified. Refetch as needed.

**Note request payloads:** Create note with `POST .../patrols/<patrol_id>/notes` with body `{ "text": "..." }`. Update with `PATCH/PUT .../notes/<note_id>`. The `patrol` is implied by the URL.

**File request payloads:** Create/update patrol files via the files endpoint; the payload typically includes `usercontent_id`, `usercontent_type`, and optionally `comment`, `ordernum`. See the API or schema for the full file upload format.

---

## Summary for mobile clients

| Goal | Recommendation |
|------|----------------|
| Fewest "has anything changed?" checks | Use **conditional GET** only where supported: **patrol types list** and **tracked-by schema**. Send **If-None-Match** (and optionally **If-Modified-Since** for patrol types). |
| Patrol types catalog | **GET .../patrols/types** with **If-None-Match**; treat **304** as "no download needed". One list call is enough for full catalog; no `updated_since` or schema options. |
| Tracked-by / segment leaders | **GET .../patrols/trackedby** with **If-None-Match**; **304** means schema/options unchanged. |
| Patrols list | No ETag. Use **filter** (e.g. **date_range** with `lower`/`upper`) and **pagination** to limit data. Store last sync time or range for incremental-style fetches. |
| Patrol and segment detail | No ETag. Refetch when you need the latest state. |
| Where conditional GET works | **Patrol types** (list and single) and **tracked-by schema** only. Patrols and segments do not support ETag/Last-Modified. |
