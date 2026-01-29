# Buoy/Gear API Architecture

## Overview

The Buoy/Gear API provides endpoints for managing ropeless fishing gear, including deployment and retrieval tracking. The system models fishing gear as subjects (gear sets) with associated sources (individual devices/buoys).

## Data Model

The buoy system uses three core Django models from the `observations` app:

- **Subject**: Represents a gear set (a trawl or single gear deployment)
- **Source**: Represents individual tracking devices/buoys attached to the gear
- **SubjectSource**: Links Sources to Subjects with temporal assignments (deployment periods)

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
- User must have permission to create gears in that SubjectGroup (checked via Casbin permission sets)
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
- Cannot deploy the same device at the same location if already deployed
- Checked in serializer: `GearCreateSerializer.validate()`

**Haul/Retrieval Event (`device_status == "hauled"`):**
- Updates `assigned_range` to: `[original_lower_bound, recorded_at)`
  - Lower bound: Preserved from existing SubjectSource (deployment time)
  - Upper bound: The retrieval timestamp, closing the deployment period
- Updates `location` to the retrieval coordinates
- Creates an Observation record at the retrieval location

**Validation:**
- Device must currently be deployed (SubjectSource must exist with active assigned_range)
- Cannot haul a device that's already hauled
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

#### 7. Observation Creation

For EVERY device event (deploy or haul), an Observation is created:

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
- `recorded_at`: Timestamp of the event (from `last_deployed` or current time)
- `additional.raw`: Complete copy of the validated request payload for audit trail

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
        │   │       └─> hauled: [existing_lower, recorded_at)
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
│              │ SubjectSource.location = deploy_location
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

### Scenario: Device deployed in Set A, then deployed in Set B

**What happens:** The system **ALLOWS** this operation, effectively moving the device from one gear set to another.

**Example Timeline:**
1. Device `DEV_001` is deployed in `SET_A` at T1
2. Device `DEV_001` is deployed in `SET_B` at T2 (without explicitly hauling from SET_A)

**Resulting Database State:**

**Sources Table:**
- One Source record for `DEV_001` (Sources are shared across gear sets)

**SubjectSources Table:**
- `SubjectSource(subject=SET_A, source=DEV_001)`:
  - `assigned_range`: `[T1, datetime.max)` - **Still shows as deployed!**
  - `location`: Original location from T1

- `SubjectSource(subject=SET_B, source=DEV_001)`:
  - `assigned_range`: `[T2, datetime.max)` - Shows as deployed
  - `location`: New location from T2

**Why This Happens:**

1. **Validation only checks within the target Subject**: The serializer validation at line 244-245:
   ```python
   subject_source = SubjectSource.objects.filter(subject=subject, source=source).first()
   ```
   Only checks if the device is deployed in the **current** Subject (SET_B), not if it's deployed in **any** Subject.

2. **`get_or_create` creates a new relationship**: In `BuoyService.process_gearset()` at line 180-182:
   ```python
   subject_source, subject_source_created = models.SubjectSource.objects.get_or_create(
       subject=subject, source=source
   )
   ```
   This creates a **new** SubjectSource for SET_B without touching the existing one for SET_A.

3. **No cross-Subject validation**: The system doesn't check if the device is currently deployed in a different gear set.

**Consequences:**

✅ **Allowed:**
- Device appears as deployed in BOTH gear sets simultaneously
- Both SubjectSources have open `assigned_range` (upper bound = `datetime.max`)
- GET requests to `/gears/?state=deployed` may return both SET_A and SET_B if the device is the only device in SET_A

❌ **Data Integrity Issues:**
- SET_A may still show as `is_active=True` if this was its only device
- Historical tracking becomes ambiguous - which gear set was the device actually with?
- No audit trail that the device was moved from SET_A to SET_B

**Prevention Validation:**

The current validation only prevents:
- Re-deploying a device at the **same location** in the **same gear set** (lines 260-266)
- Not: Re-deploying a device in a **different gear set**

**Recommended Workflow:**

To properly move a device between gear sets:

1. **Explicitly haul from SET_A:**
```json
{
  "mfr_set_id": "SET_A",
  "manufacturer_name": "EdgeTech",
  "devices": [{
    "device_id": "DEV_001",
    "device_status": "hauled",
    ...
  }]
}
```

2. **Then deploy to SET_B:**
```json
{
  "mfr_set_id": "SET_B",
  "manufacturer_name": "EdgeTech",
  "initial_deployment_date": "2024-01-20T10:00:00Z",
  "devices": [{
    "device_id": "DEV_001",
    "device_status": "deployed",
    ...
  }]
}
```

This ensures:
- SET_A's SubjectSource gets a closed `assigned_range`: `[T1, T2)`
- SET_A's `is_active` is set to `False` (if all devices hauled)
- SET_B's SubjectSource gets a new open `assigned_range`: `[T3, datetime.max)`
- Clear audit trail of the device movement

**Potential Improvement:**

Consider adding validation to check if a device is deployed in ANY gear set:

```python
# In GearCreateSerializer.validate()
if device.get("device_status") == "deployed":
    # Check if device is deployed in ANY subject (not just current subject)
    other_deployments = SubjectSource.objects.filter(
        source__id=device_id,
        assigned_range__contains=now
    ).exclude(subject=subject)

    if other_deployments.exists():
        raise ValidationError(
            f"Device {device_id} is currently deployed in another gear set. "
            "Please haul from the current gear set before deploying to a new one."
        )
```

## Error Handling

The serializer validates and raises `ValidationError` for:
- Missing required fields
- Invalid state transitions (e.g., hauling a device that's not deployed)
- Re-deploying at the same location **in the same gear set**
- User permission violations
- Missing SubjectGroup
- Future dates for deployment/updated timestamps

**Note:** The system does NOT currently prevent deploying a device in a new gear set while it's still deployed in another gear set. See "Edge Case: Moving a Device Between Gear Sets" above.

All validation errors return HTTP 400 with detailed error messages.
