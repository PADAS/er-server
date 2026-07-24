---
name: add-subject-icon
description: Add subject subtype icons to EarthRanger from a Jira request ticket — locate the ticket, pull the attached icon images, confirm subtype details, then wire up files, migration, and fixtures
---

# Add Subject Icon Skill

This skill guides you through adding new subject subtype icons to the EarthRanger/DAS system. Icon requests usually arrive as Jira tickets (typically `ERCS-*` support tickets, sometimes escalated to `ERA-*`) with the icon images attached.

## Icon Conventions

### Subject types

Every subtype belongs to one of the seeded subject types (see `observations.subjecttype` in `das/das_server/fixtures/initial_data.json`):

| value | display | gendered icons? |
|---|---|---|
| `wildlife` | Wildlife | Yes (usually) |
| `vehicle` | Vehicle | No |
| `aircraft` | Aircraft | No |
| `person` | Person | No |
| `stationary-object` | Stationary subject | No |
| `unassigned` | Unassigned | No |

### Icon naming

- **Wildlife (gendered)**: `{value}-male.svg` and `{value}-female.svg`
  - Visual convention: male animals face LEFT, female animals face RIGHT
  - The parser looks for `-male` / `-female` in filenames to select the icon
- **Everything else (vehicles, aircraft, people, stationary objects)**: a single `{value}.svg` (e.g. `truck.svg`, `car.svg`, `tourist_vehicle.svg`, `camera_trap.svg`)
  - Visual convention: vehicles face LEFT
  - Some existing icons also have color variants (`security_vehicle-black.svg`, `plane-red.svg`); only add these if the request calls for them
- The `{value}` matches the `SubjectSubType.value` field (e.g. `donkey`, `school_bus`)

### Storage location

All subject icons are stored in: `das/observations/static/`

### File format

- SVG format required for the shipped icon (scalable)
- Keep file size reasonable (< 100KB)

## Workflow

When this skill is invoked, follow these steps:

### 1. Locate the Jira ticket

If the user gives a ticket key (e.g. `ERCS-7573`), fetch it directly. If not, search for it:

- Get the cloud ID with `mcp__atlassian__getAccessibleAtlassianResources` (allenai.atlassian.net).
- Search with `mcp__atlassian__searchJiraIssuesUsingJql`, e.g.:
  `text ~ "subject subtype icons" ORDER BY created DESC` or `project = ERCS AND text ~ "icons" AND created >= -90d`
- Confirm with the user you found the right ticket before proceeding.

### 2. Read the ticket — description, comments, and attachments

Fetch the full ticket with attachments and comments:

```
mcp__atlassian__getJiraIssue
  issueIdOrKey: ERCS-XXXX
  fields: ["summary", "description", "attachment", "comment"]
```

From the **description**, extract the requested subtype names and the requesting site (e.g. swt.pamdas.org).

Read **all comments** — they frequently change the scope. Example (ERCS-7573): the ticket requested four vehicle icons, but comments established that "Pick-up Truck" was covered by the existing `truck_2`/`truck_3` icons, leaving fewer icons to actually create.

**Check for existing coverage** before creating anything: look in `das/observations/static/` and at the `observations.subjectsubtype` entries in `initial_data.json` for icons/subtypes that already satisfy part of the request. Propose reusing them instead of adding near-duplicates.

### 3. Download the attached SVG icons

Each attachment in the `attachment` field has an `id`, `filename`, `mimeType`, and a `content` URL. **Only the SVGs are the deliverable** — tickets often also carry PNG/JPEG/WebP images, but those are just example/reference pictures from the requester, not icon assets.

- Filter the attachment list to `mimeType: image/svg+xml` (or `.svg` filenames) and download only those to the scratchpad directory:

```bash
curl -sSL -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -o <scratchpad>/school-bus.svg \
  "https://allenai.atlassian.net/rest/api/3/attachment/content/<attachment-id>"
```

- Credentials: `JIRA_EMAIL` / `JIRA_API_TOKEN` env vars (an Atlassian API token). If no token is available, ask the user to either provide one or download the attachments from the ticket manually and give you the file paths.
- View each downloaded SVG with the Read tool to see what the icon looks like. Raster attachments can be viewed the same way for context (e.g. to understand what "10 Wheeler Lorry" should look like), but never copy them into the repo.
- **If the ticket has no SVG attachments** (only rasters), stop and tell the user: the ticket so far contains only reference images, and the final SVG assets are still needed (designer handoff, follow-up comment on the ticket, etc.).

### 4. Confirm subtype details with the user — REQUIRED

Before touching any files, present a proposal table and get explicit confirmation of:

1. **Subject type** — which of `wildlife` / `vehicle` / `aircraft` / `person` / `stationary-object` each icon belongs to. Do not assume `wildlife`; a vehicle request must use `vehicle`.
2. **Display name** — the human-readable name (e.g. "School Bus").
3. **Value** — the slug, lowercase snake_case (e.g. `school_bus`). This becomes both the `SubjectSubType.value` and the icon filename prefix.
4. **Gendered or single icon** — male/female variants (wildlife convention) or a single `{value}.svg` (vehicles and everything else).

Example proposal for a vehicle-icons ticket:

| Requested | Subject type | Display | Value | Icon file(s) |
|---|---|---|---|---|
| School Bus | vehicle | School Bus | `school_bus` | `school_bus.svg` |
| 10 Wheeler Lorry | vehicle | Lorry | `lorry` | `lorry.svg` |
| Suzuki Jimney | vehicle | Suzuki Jimny | `suzuki_jimny` | `suzuki_jimny.svg` |

Use AskUserQuestion (or an explicit summary the user approves) — do not proceed on assumptions. Flag anything ambiguous, e.g. whether "Suzuki Jimney" should be a generic subtype instead, or a spelling fix (Jimney → Jimny).

### 5. Validate the icon files

Always check:

- Files exist and are valid SVG format (`<svg` root element)
- Naming follows convention: `{value}.svg`, or `{value}-male.svg` / `{value}-female.svg` for gendered wildlife
- File size is reasonable (< 100KB per file)

**Facing-direction check is optional — ask the user first** (it costs time to render and inspect each icon). Include it in the step-4 AskUserQuestion or ask separately: "Should I visually validate the icons face the right direction?" Skip it when the user says the icons came from the design team already verified (e.g. a comment like "use these left facing vehicles").

If the user wants the check, the conventions are:

- Gendered icons: male faces LEFT, female faces RIGHT
- Vehicles: face LEFT

How to render on macOS (SVGs usually have tiny intrinsic sizes like 32×32, so bump them first):

```bash
# Make a 256px copy, thumbnail it, then view the PNG with the Read tool
sed -E 's/(<svg[^>]*)width="[^"]*"/\1width="256"/; s/(<svg[^>]*)height="[^"]*"/\1height="256"/' \
  icon.svg > <scratchpad>/icon-256.svg
qlmanage -t -s 256 -o <scratchpad> <scratchpad>/icon-256.svg   # writes icon-256.svg.png
```

### 6. Copy icon files

```bash
# Single icon (vehicle, aircraft, person, stationary-object)
cp <source>.svg das/observations/static/{value}.svg

# Gendered wildlife pair
cp <source-male>.svg das/observations/static/{value}-male.svg
cp <source-female>.svg das/observations/static/{value}-female.svg
```

### 7. Create migration

Create a new migration file to add the SubjectSubtype entries:

**Location**: `das/observations/migrations/XXXX_{name}.py`

**Template** (set `subject_type_value` to the confirmed subject type; chain `.add_subject_subtype(...)` for multiple subtypes of the same type):

```python
from django.db import migrations

from observations.migration_utils import TenantSubjectSubTypeLoader

subject_subtype_loader = (
    TenantSubjectSubTypeLoader(subject_type_value="vehicle")
    .add_subject_subtype(display="School Bus", value="school_bus")
    .add_subject_subtype(display="Lorry", value="lorry")
)


class Migration(migrations.Migration):

    dependencies = [
        ("observations", "{previous_migration}"),
    ]

    operations = [
        migrations.RunPython(
            code=subject_subtype_loader.load,
            reverse_code=migrations.RunPython.noop,
        )
    ]
```

If the ticket mixes subject types, build one loader per subject type and add one `RunPython` per loader (see `das/observations/migrations/0205_wildboar.py`, which loads wildlife and aircraft subtypes in the same migration). A wildlife-only example is `das/observations/migrations/0193_donkey.py`.

**Important**:
- Migration number must be sequential — check the latest with `ls das/observations/migrations/ | sort | tail`
- Update `dependencies` to point to the current latest migration
- Use `TenantSubjectSubTypeLoader` for tenant-aware loading across all tenants

### 8. Update initial_data.json

Add an entry per subtype to `das/das_server/fixtures/initial_data.json`, with `subject_type` set to the confirmed type:

```json
{
  "model": "observations.subjectsubtype",
  "fields": {
    "created_at": "YYYY-MM-DDTHH:MM:SS.sssZ",
    "updated_at": "YYYY-MM-DDTHH:MM:SS.sssZ",
    "value": "school_bus",
    "display": "School Bus",
    "subject_type": [
      "vehicle"
    ],
    "ordernum": null
  }
}
```

**Important**:
- Use the current timestamp for created_at and updated_at
- Place the entry with the other SubjectSubtype entries
- Ensure valid JSON formatting (check commas)

### 9. Verify and test

- Confirm icon files are in `das/observations/static/` and names match the `value` field
- Verify the migration file and initial_data.json entries
- Run migration: `python manage.py migrate`
- Test icon display in the UI
- Comment on / link the Jira ticket so support can follow up with the requester

## Key considerations

- **Multi-tenancy**: `TenantSubjectSubTypeLoader` handles tenant-aware loading across all tenants
- **Subject type drives everything**: gendered-vs-single icons, the loader's `subject_type_value`, and the fixture's `subject_type` — confirm it in step 4, never assume `wildlife`
- **File naming must match the value exactly**: `{value}.svg` (or `{value}-male.svg` / `{value}-female.svg` for gendered wildlife)
- **Visual convention (gendered)**: male faces LEFT, female faces RIGHT
- **Visual convention (vehicles)**: vehicles face LEFT
- **Facing checks are opt-in**: ask before spending time rendering icons to verify direction (step 5)
- **Ticket scope lives in the comments**: re-read them before finalizing the subtype list
- **Reuse before adding**: an existing icon/subtype may already cover part of the request
