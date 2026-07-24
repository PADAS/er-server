---
name: add-event-icon
description: Add event or patrol icons to EarthRanger from a Jira request ticket — locate the ticket, pull the attached SVG icons, confirm naming with the user, then drop the files into activity/static/sprite-src (no migration or fixtures needed)
---

# Add Event / Patrol Icon Skill

This skill guides you through adding new **event** and **patrol** icons to the EarthRanger/DAS system. Icon requests usually arrive as Jira tickets (`ERA-*` tasks or `ERCS-*` support tickets) with the SVG icons attached. Reference: [Adding a new Event or Patrol icon](https://allenai.atlassian.net/wiki/spaces/ER/pages/20413219761/Adding+a+new+Event+or+Patrol+icon).

Unlike subject icons (`add-subject-icon` skill), this is a **static-asset-only change**: no migration, no `initial_data.json` entries, and no sprite regeneration (that step was removed from the process). Event types and patrol types are per-tenant data configured in the admin/API — the repo only ships the icon file.

## Icon Conventions

### Naming

- **Event icon**: `{keyword}-event.svg` — e.g. `wildlife_sighting-event.svg`, `scat-event.svg`
- **Patrol icon**: `{keyword}-patrol-icon.svg` — e.g. `fence-patrol-icon.svg`, `bicycle-patrol-icon.svg`
- `{keyword}` is a lowercase snake_case description keyword, conventionally matching the EventType/PatrolType `value` (see "How icons are resolved" below)
- You will also see legacy names in the folder (`*_rep.svg`, `*_rep_SMART.svg`, bare `{name}.svg`) — do **not** use those patterns for new icons

### Storage location

All event and patrol icons live in: `das/activity/static/sprite-src/`

### File format

- SVG required (scalable); tickets sometimes attach PNG/JPEG reference images — those are context, not deliverables
- Keep file size reasonable (< 100KB)

### How icons are resolved (why the name matters)

- `EventType.icon_id` (`das/activity/models.py`) uses the type's explicit `icon` field if set, otherwise falls back to the type's `value`; if no matching file exists in `sprite-src/`, it falls back to `generic_rep`.
- `PatrolType.icon_id` works the same way.
- `StaticImageFinder` (`das/core/utils.py`) matches files in `sprite-src/` by basename, and the admin icon picker lists everything in that folder.

So the icon becomes usable the moment the file lands in `sprite-src/` with a basename that matches either the type's `value` or whatever the site admin sets in the type's `icon` field. There is nothing else to wire up in the backend.

## Workflow

When this skill is invoked, follow these steps:

### 1. Locate the Jira ticket

If the user gives a ticket key (e.g. `ERA-13547`), fetch it directly. If not, search for it:

- Get the cloud ID with `mcp__atlassian__getAccessibleAtlassianResources` (allenai.atlassian.net).
- Search with `mcp__atlassian__searchJiraIssuesUsingJql`, e.g.:
  `text ~ "event icon" ORDER BY created DESC` or `project = ERA AND text ~ "icon" AND created >= -90d`
- Confirm with the user you found the right ticket before proceeding.

### 2. Read the ticket — description, comments, and attachments

Fetch the full ticket with attachments and comments:

```
mcp__atlassian__getJiraIssue
  issueIdOrKey: ERA-XXXXX
  fields: ["summary", "description", "attachment", "comment"]
```

From the **description**, extract the requested icon names/concepts and whether they are **event** or **patrol** icons. Example (ERA-13547): a "scat event icon" request whose acceptance criteria list two icons — scat/dropping and midden (communal droppings).

Read **all comments** — they frequently change the scope or confirm the assets are final (e.g. "this one is ready to go!").

**Check for existing coverage** before adding anything: `ls das/activity/static/sprite-src/ | grep -i <keyword>`. With ~600 icons in the folder, a near-duplicate may already exist — propose reusing it instead.

### 3. Download the attached SVG icons

Each attachment in the `attachment` field has an `id`, `filename`, `mimeType`, and a `content` URL. **Only the SVGs are the deliverable.**

- Filter the attachment list to `mimeType: image/svg+xml` (or `.svg` filenames) and download only those to the scratchpad directory:

```bash
curl -sSL -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -o <scratchpad>/Droppings.svg \
  "https://allenai.atlassian.net/rest/api/3/attachment/content/<attachment-id>"
```

- Credentials: `JIRA_EMAIL` / `JIRA_API_TOKEN` env vars (an Atlassian API token). If no token is available, ask the user to either provide one or download the attachments manually and give you the file paths.
- View each downloaded SVG with the Read tool to see what the icon looks like.
- **If the ticket has no SVG attachments** (only rasters), stop and tell the user: the final SVG assets are still needed (designer handoff, follow-up comment on the ticket, etc.).

### 4. Confirm icon details with the user — REQUIRED

Attachment filenames rarely match the required naming convention (e.g. `Droppings.svg` needs to become `scat-event.svg`). Before touching any files, present a proposal table and get explicit confirmation of:

1. **Event or patrol** — determines the `-event.svg` vs `-patrol-icon.svg` suffix.
2. **Keyword** — the lowercase snake_case basename prefix. Prefer the EventType/PatrolType `value` the icon is intended for, if the ticket names one; otherwise a sensible description keyword.
3. **Final filename** — `{keyword}-event.svg` or `{keyword}-patrol-icon.svg`.

Example proposal for ERA-13547:

| Attachment | Kind | Keyword | Final filename |
|---|---|---|---|
| `Droppings.svg` | event | `scat` | `scat-event.svg` |
| `Midden.svg` | event | `midden` | `midden-event.svg` |

Use AskUserQuestion (or an explicit summary the user approves) — do not proceed on assumptions. Flag anything ambiguous, e.g. whether the requester expects the icon basename to match a specific event type id on their site.

### 5. Validate the icon files

- Files exist and are valid SVG format (`<svg` root element)
- Final names follow convention: `{keyword}-event.svg` or `{keyword}-patrol-icon.svg`
- File size is reasonable (< 100KB per file)
- No name collision with an existing file in `sprite-src/`

To visually inspect an icon on macOS (SVGs usually have tiny intrinsic sizes, so bump them first):

```bash
sed -E 's/(<svg[^>]*)width="[^"]*"/\1width="256"/; s/(<svg[^>]*)height="[^"]*"/\1height="256"/' \
  icon.svg > <scratchpad>/icon-256.svg
qlmanage -t -s 256 -o <scratchpad> <scratchpad>/icon-256.svg   # writes icon-256.svg.png, view with Read
```

### 6. Copy icon files

```bash
cp <scratchpad>/Droppings.svg das/activity/static/sprite-src/scat-event.svg
cp <scratchpad>/Midden.svg das/activity/static/sprite-src/midden-event.svg
```

That's it — no migration, no fixtures, no sprite rebuild.

### 7. Verify and follow up

- Confirm the files are in `das/activity/static/sprite-src/` with the agreed names
- Commit to a feature branch and PR into `develop` (the icons ship when the branch is merged)
- Comment on / link the Jira ticket so the requester knows the icon basename to use in the event/patrol type's `icon` field (or to name their type `value` to match)

## Key considerations

- **Static asset only**: adding the file is the whole backend change — event/patrol types are per-tenant admin data, not repo fixtures
- **Naming is the contract**: the basename must match the type's `value` or its `icon` field, or the type silently falls back to the generic icon (`generic_rep`)
- **Suffix by kind**: `-event.svg` for event icons, `-patrol-icon.svg` for patrol icons; never copy the legacy `_rep` pattern
- **Attachment names ≠ final names**: always rename per convention and confirm with the user first (step 4)
- **Ticket scope lives in the comments**: re-read them before finalizing the icon list
- **Reuse before adding**: ~600 icons already exist in `sprite-src/`; check for coverage first
