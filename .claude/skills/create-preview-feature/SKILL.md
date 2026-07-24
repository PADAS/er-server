---
name: create-preview-feature
description: Add a new previewFeatures flag (short-lived per-tenant rollout gate) to the PREVIEW_FEATURES registry, wire up its read site, and add registry tests
---

# Create Preview Feature Skill

This skill adds a new **preview feature** — a short-lived, per-tenant rollout gate — to EarthRanger, following [docs/topics/Developing-ER/feature-flags.md](../../../docs/topics/Developing-ER/feature-flags.md). Read that doc if anything here is unclear; it is the source of truth.

A preview feature keeps an unfinished feature dark in mainline, is flipped on per-tenant (via TMS, no release) or for everyone (via `global_override`, one ER PR), and is **deleted once the rollout is complete**. Adding one is an **ER-only change** — no TMS schema update.

> **Delegation**: implementation work in the das repo must be done by the `backend-developer` agent. Use this skill to gather inputs and drive the workflow; delegate the code edits.

## Workflow

### 1. Confirm a preview feature is the right tool

Ask (or infer from context) whether this flag is:

- **A transitional rollout gate** (temporary; deleted after rollout) → preview feature. Continue.
- **Durable per-site capability configuration** ("what a site sees", indefinite lifespan) → a **typed feature flag** on the `FeatureFlags` dataclass in `das/utils/tenant/dataclass.py` instead, which needs a coordinated TMS schema change. Stop and tell the user.

If unsure, start as a preview feature — promoting later is cheaper than carrying a permanent stringly-typed entry.

Also check none of these anti-patterns apply:

- Do **not** extend the legacy `Features` enum in `das/utils/features.py` (`features.tms` is a relic; never add entries).
- Do **not** add a Django setting as a kill switch in front of the feature — the preview feature is the single gate.
- Preview features cannot do per-user gating or percentage rollouts (per-tenant only, resolved once per request).

### 2. Gather information

Ask the user for anything not already provided:

- **Feature name** — snake_case, e.g. `events_vector_tiles`. If it gates a Django admin page, use the `<feature>_admin_enabled` naming convention.
- **Description** — one line saying what it gates; conventionally ends with "Set global_override=True to expose it for every tenant at once."
- **Default** — almost always `False` (opt-in). Push back if the user wants `True` for a rollout gate.
- **What it gates** — a Django admin page, an API/serializer behaviour, or something else. This determines the read-site pattern in step 4.

### 3. Register the feature

Add an entry to `PREVIEW_FEATURES` in `das/utils/tenant/preview_features.py`:

```python
PREVIEW_FEATURES: dict[str, PreviewFeature] = {
    # ...existing entries...
    "your_feature_name": PreviewFeature(
        default=False,
        description="Per-tenant gate for <what it gates>. "
        "Set global_override=True to expose it for every tenant at once.",
    ),
}
```

Leave `global_override` unset (`None`) — it is the later "public for everyone" / "emergency kill" lever, not something a new feature ships with.

### 4. Wire up the read site

**Generic code path:**

```python
from utils.tenant.preview_features import get_preview_feature

if get_preview_feature("your_feature_name"):
    ...
```

Reading an unregistered name raises `UnknownPreviewFeature` — that's intentional typo protection, so the registry entry (step 3) must land with (or before) the read site.

**Django admin page** — use `PreviewFeatureAdminMixin` from `das/core/common.py` instead of hand-rolled permission checks:

```python
from core.common import PreviewFeatureAdminMixin

@admin.register(models.YourModel)
class YourModelAdmin(PreviewFeatureAdminMixin, admin.ModelAdmin):
    preview_feature = "your_feature_admin_enabled"
    ...
```

The mixin overrides all `has_*_permission` methods to consult the feature at request time, so the admin is registered but hidden (superusers included) until the feature is on. Do **not** use `AdminFeatureFlag` for new admin gates — that import-time pattern is retired for admin gating.

### 5. Add registry tests

Extend `TestRegistry` in `das/utils/tests/test_preview_feature_registry.py`, mirroring the existing pattern (test names are descriptive sentences; grouped in the class):

```python
def test_your_feature_name_is_registered(self):
    feature = PREVIEW_FEATURES["your_feature_name"]
    assert isinstance(feature, PreviewFeature)
    assert feature.default is False
    assert feature.description

def test_your_feature_name_has_no_global_override_by_default(self):
    assert PREVIEW_FEATURES["your_feature_name"].global_override is None
```

Also test the gated behaviour itself at the read site (e.g. admin hidden when off / visible when on — see `das/core/tests/test_preview_feature_admin.py` and `das/activity/tests/test_admin_community_gate.py` for reference patterns). To fake a tenant value in tests, patch `get_tenant_settings` where the reader imports it:

```python
from types import SimpleNamespace
from unittest.mock import patch

settings = SimpleNamespace(preview_features={"your_feature_name": True})
with patch("utils.tenant.preview_features.get_tenant_settings", return_value=settings):
    ...
```

Run the tests before declaring done.

### 6. Tell the user how to enable it

Include this in your final summary:

- **Local dev**: add to `das/.env` — `PREVIEW_FEATURES={"your_feature_name": true}` (applies when using `DjangoSettingsClient`; if running `TestClient`, set the key in `das/core/fixtures/tenant-response.json`'s `previewFeatures` block instead). Never set `global_override`/`default` in the registry just to test locally.
- **One tenant, no release**: `PATCH /v1.0/tenants/{tenant_id}?key={TMS_API_KEY}` with body `{"previewFeatures": {"your_feature_name": true}}`. The patch merges key-by-key; TMS doesn't validate keys, so it must match the registered name exactly. Values must be booleans.
- **Everyone**: a follow-up one-line ER PR setting `global_override=True` on the entry.
- **End state**: once fully rolled out, delete the feature and its checks — don't leave `global_override=True` forever.

## Resolution precedence (for reference)

`get_preview_feature(name)` resolves: **1.** `global_override` (if not `None`, wins for every tenant) → **2.** per-tenant value from the tenant payload's `previewFeatures` dict → **3.** registered `default`.

## Files touched

| File | Change |
| --- | --- |
| `das/utils/tenant/preview_features.py` | New `PREVIEW_FEATURES` entry |
| Call site (app code or `ModelAdmin`) | `get_preview_feature(...)` or `PreviewFeatureAdminMixin` |
| `das/utils/tests/test_preview_feature_registry.py` | Registry tests for the new entry |
| Call-site tests | Gated-behaviour tests (on/off) |
