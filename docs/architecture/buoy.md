# Buoy/Gear API Architecture

## Overview

The Buoy/Gear API provides endpoints for managing ropeless fishing gear, including deployment and retrieval tracking. The system models fishing gear as subjects (gear sets) with associated sources (individual devices/buoys).

## Data Model

The buoy system uses three core Django models from the `observations` app:

- **Subject**: Represents a gear set (a trawl or single gear deployment)
- **Source**: Represents individual tracking devices/buoys attached to the gear
- **SubjectSource**: Links Sources to Subjects with temporal assignments (deployment periods)

## GET API: Reading Gear Sets

### Endpoints
- `GET /api/v1.0/gear/` — list all gearsets (paginated)
- `GET /api/v1.0/gear/<id>/` — retrieve a single gearset

### Queryset: Subject-based

The list and detail views use `Subject` as the root queryset model — one database row per gearset. All device data is reached via prefetched `SubjectSource` rows:

```python
Subject.objects.filter(
    subject_subtype__in=["ropeless_buoy_device", BUOY_GEAR_SUBJECT_SUBTYPE]
).prefetch_related(
    "groups",
    Prefetch(
        "subjectsources",
        queryset=SubjectSource.objects.select_related("source"),
        to_attr="all_subjectsources",
    ),
)
```

This guarantees one result per gearset regardless of how many devices (Sources/SubjectSources) belong to it. The `all_subjectsources` prefetch loads all SubjectSources and their Sources in exactly **2 queries** total, avoiding N+1 queries when serializing the device list. Device location is read directly from `SubjectSource.location` (see below), so no additional queries against the partitioned Observations table are needed.

### Serializer: GearSerializer

`GearSerializer` operates on a `Subject` instance (`obj`). All fields are read-only.

**Response shape:**
```json
{
  "id": "<subject.id>",
  "display_id": "<subject.additional.display_id or subject.name>",
  "status": "deployed | hauled",
  "type": "single | trawl",
  "manufacturer": "<subject.additional.manufacturer or first SubjectGroup name>",
  "last_updated": "<ISO 8601>",
  "devices": [
    {
      "device_id": "<source.id>",
      "mfr_device_id": "<source.manufacturer_id>",
      "label": "a | b | c ...",
      "location": {"latitude": float, "longitude": float},
      "last_updated": "<ISO 8601>",
      "last_deployed": "<ISO 8601>"
    }
  ]
}
```

### Timestamps: last_updated and recorded_at

Understanding how timestamps flow through the system is important for correct interpretation of the GET response.

#### On write (POST)

Each device payload carries two time fields:

| Field | Meaning | Where stored |
|-------|---------|--------------|
| `recorded_at` | When the GPS position fix was taken (the event time) | `Observation.recorded_at` and `SubjectSource.assigned_range` bounds |
| `last_updated` | Manufacturer-provided timestamp for the device update | `source.additional["last_updated"]` and `subject.additional["last_updated"]` |

For location updates, `recorded_at` and `last_updated` typically carry the same value since the location fix time *is* the update time. If `recorded_at` is absent from the payload, the service derives it from `last_deployed` (for deploy events) or `last_updated` (for haul events), falling back to current time.

#### On read (GET response)

**Gearset-level `last_updated`** — `GearSerializer.get_last_updated(obj)`:
1. Reads `subject.additional["last_updated"]` (the manufacturer timestamp written at POST time)
2. Falls back to `subject.updated_at` (Django auto-timestamp)

**Device-level `last_updated`** — built in `_compute_devices()`:
1. Reads `source.additional["last_updated"]` (the per-device manufacturer timestamp written at POST time)
2. Falls back to `source.updated_at`

**Device `location`** — read directly from `SubjectSource.location`. `BuoyService` sets this field on every gear observation (deploy, haul, and mid-deployment position update), so it always reflects the most recent reported position. Reading from `SubjectSource.location` avoids querying the partitioned Observations table at read time.

**Device `last_deployed`** — read from `SubjectSource.assigned_range.lower`, which is set to `recorded_at` at deploy time.

#### Summary

```
POST payload.recorded_at  ──► Observation.recorded_at
                          ──► SubjectSource.assigned_range.lower  ──► GET device.last_deployed
POST payload.last_updated ──► source.additional["last_updated"]   ──► GET device.last_updated
                          ──► subject.additional["last_updated"]  ──► GET gearset.last_updated
BuoyService (every POST)  ──► SubjectSource.location             ──► GET device.location
```

### List filters

| Parameter | Behaviour |
|-----------|-----------|
| `state=deployed\|hauled` | Filters `Subject.is_active` (True = deployed, False = hauled) |
| `updated_since=<date>` | Delegates to `SubjectQuerySet.by_updated_since()` |
| `lat`, `lon`, `max_nm_range` | Spatial filter via `filter_by_bbox()`: returns subjects whose latest device observation falls within the bounding box |
| `include_empty_location` | When false (default), devices with no real location (0,0 or null) are excluded from the `devices` array |

---

## POST API: Creating/Updating Gear Sets

### Endpoint
`POST /api/v1.0/gears/`

### Business Rules

#### 1. Request Processing Flow

When a POST request is received at `GearsListCreateView.create()`:

1. **Validation**: The request data is validated using `GearCreateSerializer`
2. **Processing**: Validated data is passed to `BuoyService.process_gearset()`
3. **Response**: Returns the created/updated Subject ID and a 201 status code

```python
@transaction.atomic
def create(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    validated_data = serializer.validated_data

    subject, observations = BuoyService.process_gearset(validated_data, user=request.user)
    return Response(
        {
            "detail": "Gears successfully processed",
            "set_id": str(subject.id),
        },
        status=201,
        headers={"Location": reverse("gear-view", args=[str(subject.id)])},
    )
```

#### 2. Set ID Resolution

The system uses multiple strategies to determine the `set_id` (Subject ID):

**Priority Order:**
1. **Explicit `set_id`**: If provided in the request, use it directly
2. **Lookup by `mfr_set_id`**: Search for existing Subject where `Subject.name == mfr_set_id`
3. **Infer from devices**: Find an active Subject that has SubjectSource relationships for ALL device_ids in the request
4. **Generate new UUID**: If `mfr_set_id` is provided but no existing Subject found, create a new UUID

**Validation Rules:**
- `initial_deployment_date` is REQUIRED for new gear sets (when Subject doesn't exist)
- `initial_deployment_date` is OPTIONAL for updates to existing gear sets

#### 3. Subject (Gear Set) Creation/Update

**Create New Subject:**
- Occurs when no Subject exists with the resolved `set_id`
- Subject is created with:
  - `id`: The resolved `set_id` (UUID)
  - `name`: The `mfr_set_id` (manufacturer's set identifier)
  - `subject_subtype`: `"ropeless_buoy_gearset"` (constant: `BUOY_GEAR_SUBJECT_SUBTYPE`)
  - `additional`: JSON field containing:
    - `display_id`: Display identifier for the UI (defaults to `mfr_set_id`)
    - `manufacturer`: Manufacturer name from request
    - `last_updated`: Timestamp from request
    - Any custom data from `set_additional_data`
  - `is_active`: Defaults to `True`

**Update Existing Subject:**
- If Subject already exists with the `set_id`:
  - Updates `name` if `mfr_set_id` has changed
  - Merges new data into `additional` field:
    - Updates `display_id` if provided
    - Updates `manufacturer` if provided
    - Updates `last_updated` if provided
    - Merges `set_additional_data` into existing additional field
  - Recalculates `is_active` based on device deployment states (see below)

**Subject Group Assignment:**
- The Subject is added to a SubjectGroup based on `manufacturer_name`
- The SubjectGroup must exist before gear creation (validated in serializer)
- User must have permission to create gears in that SubjectGroup
- The relationship is many-to-many, so a Subject can belong to multiple SubjectGroups

#### 4. Source (Device) Creation/Update

For each device in the `devices` array:

**Create New Source:**
- Sources are identified by `(provider, manufacturer_id)` tuple (unique constraint)
- When creating a new Source:
  - `id`: Uses `device_id` from request (UUID)
  - `manufacturer_id`: The `mfr_device_id` (manufacturer's device identifier)
  - `provider`: References the default SourceProvider
  - `additional`: JSON field containing:
    - `last_updated`: Timestamp from device data

**Update Existing Source:**
- If a Source exists with matching `(provider, manufacturer_id)`:
  - The existing Source is reused (even if `device_id` differs)
  - Updates `additional.last_updated` if provided in request
  - **Important**: The Source `id` is NOT updated; only the `additional` field changes

#### 5. SubjectSource (Device-to-Gear Assignment) Creation/Update

SubjectSource represents the relationship between a Source (device) and Subject (gear set) with temporal bounds.

**Get or Create:**
```python
subject_source, created = SubjectSource.objects.get_or_create(
    subject=subject,
    source=source
)
```

**Deployment Event (`device_status == "deployed"`):**
- Sets `assigned_range` to: `[recorded_at, datetime.max)`
  - Lower bound: The deployment timestamp (`recorded_at` or current time)
  - Upper bound: `datetime.max` (infinity) indicating device is currently deployed
- Updates `location` to the deployment coordinates
- Creates an Observation record at the deployment location

**Validation:**
Validation for deployment payloads is performed in the serializer (`GearCreateSerializer.validate()`), which enforces payload structure and general business rules described below. It does **not** currently enforce any rule that prevents redeploying the same device at the same location; such a rule would need to be implemented separately if desired.

**Device already deployed on another gearset:**
If a device in the payload is already deployed on a *different* Subject (another gearset with an open `assigned_range`), the system compares the payload’s deployment time with the existing deployment’s start:

- **Older gearset (reject):** If the payload’s `recorded_at` is **before** the existing deployment’s start (`assigned_range.lower`), the request is **rejected** with HTTP 400. The device is considered to be on a newer gearset; posting an older deployment would conflict. The error message includes the device id and the newer gearset’s set_id.
- **Newer time (accept):** If the payload’s `recorded_at` is **strictly after** the existing deployment’s start, the system **accepts the new deployment** and **closes the previous gearset entirely** (see below).

When accepting:
- Before processing the new gearset, the service finds every Subject that has at least one device in the payload still deployed there (open upper bound).
- For each such previous Subject, it **closes every** `SubjectSource` on that subject that is still deployed (open upper bound)—i.e. it hauls the whole gearset, including devices that do *not* appear in the new payload. The haul time used is the **earliest** `recorded_at` among all devices in the payload that were previously deployed on that Subject.
- Each such subject’s `is_active` is set to `False`.
- The new gearset is then processed as normal; devices in the payload are assigned to it with an open `assigned_range`.

**Multi-device payloads and timestamps:** When multiple devices in a single payload were previously deployed on the same Subject and have different `recorded_at` values, the **earliest** of those timestamps is used as the haul time for that entire previous gearset. API clients should use a consistent `recorded_at` across all devices in a single gearset deployment payload to avoid ambiguity about when the previous gearset was hauled.

So: **newer deployment wins** (previous gearset is fully closed); **older deployment is rejected** (400).

**Haul/Retrieval Event (`device_status == "hauled"`):**
- Updates `assigned_range` to: `[original_lower_bound, recorded_at)`
  - Lower bound: Preserved from existing SubjectSource (deployment time)
  - Upper bound: The retrieval timestamp, closing the deployment period
- Updates `location` to the retrieval coordinates
- Creates an Observation record at the retrieval location

**Haul of a never-before-seen device (deploy-and-haul in one request):**
A haul payload may legitimately introduce a device that has no prior `SubjectSource` — for example, when an extra device is discovered on a trawl during retrieval and reported for the first time alongside the haul event. In this case the service creates the `SubjectSource` atomically with:
  - Lower bound: `device.last_deployed` from the payload (falling back to `recorded_at` if absent)
  - Upper bound: `recorded_at` of the haul event
This produces a meaningful deployment window for the newly-discovered device rather than defaulting the lower bound to the min timestamp.

**Validation:**
- If the device already has a `SubjectSource`, it must currently be deployed; hauling an already-hauled device is rejected.
- A device with no prior `SubjectSource` is permitted in a haul payload (see deploy-and-haul above).
- Checked in serializer: `GearCreateSerializer.validate()`

#### 6. Auto-Haul Behavior

When any device in a gearset is hauled, the system **automatically hauls all other deployed devices** in the same gearset:

```python
# If any device was hauled, auto-haul all remaining deployed devices
if any_device_hauled:
    haul_time = <recorded_at from first hauled device>
    deployed_subject_sources = SubjectSource.objects.filter(
        subject=subject,
        assigned_range__endswith=datetime.max,  # Still deployed
    )
    for ss in deployed_subject_sources:
        ss.assigned_range = DateTimeTZRange(lower=ss.assigned_range.lower, upper=haul_time)
        ss.save()
```

**Why Auto-Haul?**
- Fishing gear sets (trawls) are hauled as a unit - all devices come up together
- Manufacturers may only report one device in haul notifications due to operational constraints
- This prevents "orphaned" deployed devices when the gearset is physically retrieved

#### 7. Subject Active State Management

After processing all devices (including auto-haul), the system determines if the Subject should be active:

```python
max_upper = DEFAULT_ASSIGNED_RANGE[1]  # datetime.max
assigned_ranges = SubjectSource.objects.filter(subject=subject).values_list("assigned_range", flat=True)
all_hauled = assigned_ranges.exists() and all(ar.upper != max_upper for ar in assigned_ranges)
if all_hauled:
    subject.is_active = False
    subject.save()
```

**Business Rule:**
- A Subject (gear set) is `is_active = True` if ANY of its SubjectSources have an active deployment
- A Subject is `is_active = False` if ALL of its SubjectSources are hauled (upper bound is not `datetime.max`)
- With auto-haul, hauling ANY device effectively hauls the entire gearset

#### 8. Observation Creation

For every device event **in the payload** (deploy or haul), an Observation is created. Note that auto-hauled devices (devices on the same gearset not present in the payload) and devices on automatically closed previous gearsets do **not** receive synthetic Observations — only devices explicitly included in the request do.

```python
observation = Observation.objects.create(
    source=source,
    location=device_location,
    recorded_at=recorded_at,
    additional={"raw": serializable_validated}
)
```

**Fields:**
- `source`: References the device Source
- `location`: Point(longitude, latitude) of the event
- `recorded_at`: Timestamp of the event — taken from the payload's `recorded_at` field; if absent, falls back to `last_deployed` for deployed events, `last_updated` for hauled events, then current time if neither is available
- `additional.raw`: Complete copy of the validated request payload for audit trail

#### 9. SubjectSource.location — Live Position Cache

`BuoyService` writes `subject_source.location` on **every** processed gear observation — not just deploy/haul events, but also mid-deployment position updates. This makes `SubjectSource.location` the authoritative cached position for a device, readable without any additional queries.

**Backfilling existing data:** The management command `backfill_gear_subjectsource_location` populates `SubjectSource.location` for all currently deployed (open-ended `assigned_range`) gear SubjectSources using data from `LatestObservationSource`. Run it once after deploying the code that enables live position caching:

```bash
python manage.py backfill_gear_subjectsource_location [--batch-size 500] [--dry-run]
```

This command is safe to delete once all environments have been migrated.

## Data Flow Diagram

```
POST /api/v1.0/gears/
    │
    ├─> GearCreateSerializer.validate()
    │   ├─> Resolve set_id
    │   ├─> Validate manufacturer_name exists as SubjectGroup
    │   ├─> Validate user has permission for SubjectGroup
    │   ├─> Validate device state transitions (deploy/haul)
    │   └─> Ensure initial_deployment_date for new gear sets
    │
    └─> BuoyService.process_gearset()
        │
        ├─> Close previous deployments (if any device already deployed on another gearset)
        │   ├─> If payload recorded_at < existing deployment start → reject 400 (older gearset)
        │   ├─> For each such previous subject: close all SubjectSources with open upper bound (haul entire gearset)
        │   ├─> Set assigned_range upper = new deployment recorded_at for each
        │   └─> Set is_active=False for each affected subject
        │
        ├─> Get or Create Subject
        │   ├─> Set name = mfr_set_id
        │   ├─> Set additional.display_id
        │   ├─> Set additional.manufacturer
        │   └─> Add to SubjectGroup
        │
        ├─> For each device:
        │   │
        │   ├─> Get or Create Source
        │   │   └─> Unique on (provider, manufacturer_id)
        │   │
        │   ├─> Get or Create SubjectSource
        │   │   ├─> Set location = device location
        │   │   └─> Set assigned_range based on device_status:
        │   │       ├─> deployed: [recorded_at, datetime.max)
        │   │       ├─> hauled (existing SubjectSource): [existing_lower, recorded_at)
        │   │       └─> hauled (new SubjectSource):     [last_deployed, recorded_at)
        │   │
        │   └─> Create Observation
        │       ├─> location = device location
        │       ├─> recorded_at = event time
        │       └─> additional.raw = full payload
        │
        └─> Update Subject.is_active
            └─> False if all SubjectSources are hauled, else True
```

## State Transitions

### Gear Set (Subject) States

```
┌─────────────┐
│   Created   │ (is_active = True)
│             │
│  First      │
│  Deploy     │
└──────┬──────┘
       │
       │ All devices deployed
       v
┌─────────────┐
│   Deployed  │ (is_active = True)
│             │
│  Tracking   │
│  Location   │
└──────┬──────┘
       │
       │ Any device hauled (auto-hauls all)
       v
┌─────────────┐
│    Hauled   │ (is_active = False)
│             │
│  Complete   │
└─────────────┘
       │
       │ Can be re-deployed
       v
┌─────────────┐
│ Re-deployed │ (is_active = True)
└─────────────┘
```

**Note:** With auto-haul enabled, there is no "Partially Hauled" state. When any device is hauled, all devices in the gearset are automatically hauled together.

### Device (Source/SubjectSource) States

```
┌──────────────┐
│     New      │
│   Source     │
└──────┬───────┘
       │
       │ POST with device_status="deployed"
       v
┌──────────────┐
│   Deployed   │ SubjectSource.assigned_range = [T1, ∞)
│              │ SubjectSource.location = deploy_location  (updated on every POST)
└──────┬───────┘
       │
       │ POST with device_status="hauled"
       v
┌──────────────┐
│    Hauled    │ SubjectSource.assigned_range = [T1, T2)
│              │ SubjectSource.location = haul_location
└──────────────┘
       │
       │ Can be re-deployed (creates new SubjectSource or updates range)
       v
┌──────────────┐
│ Re-deployed  │ SubjectSource.assigned_range = [T3, ∞)
└──────────────┘
```

## Example Scenarios

### Scenario 1: New Single Gear Deployment

**Request:**
```json
{
  "manufacturer_name": "EdgeTech",
  "mfr_set_id": "SET_001",
  "deployment_type": "single",
  "initial_deployment_date": "2024-01-15T10:00:00Z",
  "devices": [
    {
      "device_id": "123e4567-e89b-12d3-a456-426614174000",
      "mfr_device_id": "DEV_A001",
      "device_status": "deployed",
      "last_deployed": "2024-01-15T10:00:00Z",
      "last_updated": "2024-01-15T10:00:00Z",
      "location": {"latitude": 42.5, "longitude": -71.2}
    }
  ]
}
```

**Result:**
- **Subject created:**
  - `id`: new UUID
  - `name`: "SET_001"
  - `is_active`: True
  - `additional.display_id`: "SET_001"
  - `additional.manufacturer`: "EdgeTech"

- **Source created:**
  - `id`: "123e4567-e89b-12d3-a456-426614174000"
  - `manufacturer_id`: "DEV_A001"

- **SubjectSource created:**
  - `subject`: references Subject
  - `source`: references Source
  - `assigned_range`: [2024-01-15T10:00:00Z, datetime.max)
  - `location`: Point(-71.2, 42.5)

- **Observation created:**
  - `source`: references Source
  - `location`: Point(-71.2, 42.5)
  - `recorded_at`: "2024-01-15T10:00:00Z"

### Scenario 2: Hauling a Deployed Gear

**Request:**
```json
{
  "mfr_set_id": "SET_001",
  "manufacturer_name": "EdgeTech",
  "deployment_type": "single",
  "devices": [
    {
      "device_id": "123e4567-e89b-12d3-a456-426614174000",
      "mfr_device_id": "DEV_A001",
      "device_status": "hauled",
      "last_deployed": "2024-01-15T16:00:00Z",
      "last_updated": "2024-01-15T16:00:00Z",
      "location": {"latitude": 42.6, "longitude": -71.3}
    }
  ]
}
```

**Result:**
- **Subject updated:**
  - `is_active`: False (all devices hauled)

- **Source:** No changes (already exists)

- **SubjectSource updated:**
  - `assigned_range`: [2024-01-15T10:00:00Z, 2024-01-15T16:00:00Z)
  - `location`: Point(-71.3, 42.6) - updated to haul location

- **Observation created:**
  - `location`: Point(-71.3, 42.6)
  - `recorded_at`: "2024-01-15T16:00:00Z"

### Scenario 3: Trawl Gear (Multiple Devices)

**Request:**
```json
{
  "manufacturer_name": "BlueOceanGear",
  "mfr_set_id": "TRAWL_005",
  "deployment_type": "trawl",
  "initial_deployment_date": "2024-01-20T08:00:00Z",
  "devices": [
    {
      "device_id": "aaa-111",
      "mfr_device_id": "BOG_001",
      "device_status": "deployed",
      "last_deployed": "2024-01-20T08:00:00Z",
      "last_updated": "2024-01-20T08:00:00Z",
      "location": {"latitude": 43.0, "longitude": -70.5}
    },
    {
      "device_id": "bbb-222",
      "mfr_device_id": "BOG_002",
      "device_status": "deployed",
      "last_deployed": "2024-01-20T08:05:00Z",
      "last_updated": "2024-01-20T08:05:00Z",
      "location": {"latitude": 43.1, "longitude": -70.6}
    }
  ]
}
```

**Result:**
- **Subject created:**
  - One Subject for the entire trawl set
  - `name`: "TRAWL_005"
  - `is_active`: True

- **Sources created:**
  - Two separate Sources (one per device)

- **SubjectSources created:**
  - Two SubjectSources linking both devices to the same Subject
  - Both with active assigned_ranges

- **Observations created:**
  - Two Observations (one per device)

### Scenario 4: Trawl Haul with Auto-Haul

If only ONE device from the trawl above is included in the haul notification, the system **automatically hauls all other devices**:

**Request:**
```json
{
  "mfr_set_id": "TRAWL_005",
  "manufacturer_name": "BlueOceanGear",
  "deployment_type": "trawl",
  "devices": [
    {
      "device_id": "aaa-111",
      "mfr_device_id": "BOG_001",
      "device_status": "hauled",
      "last_deployed": "2024-01-20T14:00:00Z",
      "last_updated": "2024-01-20T14:00:00Z",
      "location": {"latitude": 43.05, "longitude": -70.55}
    }
  ]
}
```

**Result:**
- **Subject:** `is_active` set to `False` (all devices hauled via auto-haul)
- **SubjectSource for BOG_001:** assigned_range closed to `[2024-01-20T08:00:00Z, 2024-01-20T14:00:00Z)`
- **SubjectSource for BOG_002:** **auto-hauled** with assigned_range closed to `[2024-01-20T08:05:00Z, 2024-01-20T14:00:00Z)`

**Note:** The auto-haul uses the `recorded_at` timestamp from the first hauled device in the request. This ensures all devices in the gearset have consistent haul timestamps.

### Scenario 5: Haul Payload Adds a New Device

A trawl gearset was originally created with one device. When the gear is hauled, the integration reports **two** devices — the original one plus a newly-discovered device that was never previously announced to the API. Both are marked `hauled` in the same payload.

**Initial state:**
- `SET_527E` exists with one deployed device `DEV_50F8` (`assigned_range` = `[2026-04-11T19:59:04Z, ∞)`).

**Request:**
```json
{
  "deployment_type": "trawl",
  "manufacturer_name": "RMWHub",
  "set_id": "527e5aed-36fe-4ea4-80d0-4b1153d274bb",
  "devices_in_set": 2,
  "devices": [
    {
      "device_id": "50f811ee-1728-47c5-aa7b-66641555ee0b",
      "last_deployed": "2026-04-11T19:59:04Z",
      "last_updated": "2026-04-17T16:54:17Z",
      "device_status": "hauled",
      "location": {"latitude": 44.6157302, "longitude": -67.50190767}
    },
    {
      "device_id": "5b1ea16b-c8be-47f5-9ace-93109f422ed0",
      "last_deployed": "2026-04-11T20:00:02Z",
      "last_updated": "2026-04-17T16:54:17Z",
      "device_status": "hauled",
      "location": {"latitude": 44.61586943, "longitude": -67.5012982}
    }
  ]
}
```

**Result:**
- **SubjectSource for `DEV_50F8`:** `assigned_range` closed to `[2026-04-11T19:59:04Z, 2026-04-17T16:54:18Z)` (preserving the original lower bound).
- **SubjectSource for `DEV_5B1E`:** **created** with `assigned_range` `[2026-04-11T20:00:02Z, 2026-04-17T16:54:18Z)` — the lower bound is taken from the payload's `last_deployed` so the device has a meaningful deployment window.
- **Subject `SET_527E`:** `is_active` set to `False` (every `SubjectSource` is now hauled).
- **Observations:** Two Observations are written — one per device in the payload — at the haul location.

This avoids requiring clients to send a separate deploy payload for devices that are only discovered at retrieval time.

## Permission Requirements

1. **Authentication**: User must be authenticated (`IsAuthenticated`)
2. **SubjectGroup Access**: User must have permission to create gears in the specified manufacturer's SubjectGroup
3. **Location Permission**: `GearLocationPermission` - certain manufacturers can create gears anywhere; others must provide valid lat/lon
4. **Object Permissions**: Standard object-level permissions via `StandardObjectPermissions`

## Transaction Guarantees

The entire `create()` operation is wrapped in `@transaction.atomic`, ensuring:
- All Subject, Source, SubjectSource, and Observation changes are committed together
- On any error, all changes are rolled back
- Data consistency is maintained across related models

## Edge Case: Moving a Device Between Gear Sets

### Current behavior: accept new deployment, close previous

When a device is deployed in **Set A** and then included in a **new** gearset **Set B** (with a different `set_id`), the system **accepts the new deployment** and **closes the previous one**:

1. **Before** creating/updating the new gearset, `BuoyService.process_gearset()` finds any Subject that has at least one device (from the payload) still deployed there (open `assigned_range`).
2. For each such previous Subject, it **closes every** `SubjectSource` on that subject that is still deployed (open upper bound)—i.e. it hauls the **entire** previous gearset, including devices that are not in the new payload. The upper bound is set to the new deployment’s `recorded_at` (no additional time offset is applied).
3. Each such previous subject’s `is_active` is set to `False`.
4. The new gearset is then processed normally; the devices in the payload are assigned to it with an open `assigned_range`.

**Example timeline:**
1. Device `DEV_001` is deployed in `SET_A` at T1 → SubjectSource(SET_A, DEV_001) has `assigned_range` [T1, ∞).
2. Same device is deployed in `SET_B` at T2 (POST with a new `set_id` for SET_B).

**Resulting database state:**
- **Subject A:** Every `SubjectSource` on SET_A that was still deployed is closed: `assigned_range` upper set to T2 (same for all). SET_A’s `is_active` is set to `False`. This includes devices that were on SET_A but do *not* appear in the new payload.
- **SubjectSource(SET_B, DEV_001):** New record with `assigned_range` `[T2, ∞)` and location from the new request.

So the **latest deployment is always the current one**; the previous gearset is closed out automatically when the payload time is **strictly after** the existing deployment’s start. You do not need to explicitly haul from SET_A before deploying to SET_B—posting the new gearset does both. **Posting an older gearset** (payload `recorded_at` earlier than the current deployment’s start) is **rejected** with HTTP 400 so that a newer deployment is not overwritten.

**Optional explicit workflow:**
You can still haul from SET_A first and then deploy to SET_B; the result is consistent. The accept-and-close behavior is for cases where the client only sends the new deployment.

**Older gearset rejected:**
If the device is already deployed on SET_B (newer) and a request is sent for SET_A with an earlier `recorded_at`, the request is **rejected** with HTTP 400 (`OlderGearsetRejectedError`). The response body explains that the device is already deployed on a newer gearset and the payload’s deployment time is before that deployment.

## Error Handling

The serializer validates and raises `ValidationError` for:
- Missing required fields
- Hauling a device whose existing `SubjectSource` is already closed (already hauled). Hauling a device with no prior `SubjectSource` is accepted and processed as deploy-and-haul in one step.
- User permission violations
- Missing SubjectGroup
- Future dates for deployment/updated timestamps

**Device moved to another gearset:**
If a device is deployed in a new gearset while still deployed elsewhere, the previous deployment is closed automatically when the new deployment’s time is **strictly after** the existing deployment’s start (see "Edge Case: Moving a Device Between Gear Sets"). If the new payload’s deployment time is **at or before** the existing deployment’s start (older or same-time gearset), the request is rejected with 400.

All validation errors return HTTP 400 with detailed error messages.
