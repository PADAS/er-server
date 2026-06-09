# Feature Flags

EarthRanger has **two current per-tenant flagging systems**, supplied by the Tenant Management Service and distinguished by how long the flag lives, plus one truly legacy artifact you should leave alone. The choice between the two is by **longevity and purpose** — see [Choosing where a new flag goes](#choosing-where-a-new-flag-goes).

- **Typed feature flags** — long-lived, strongly-typed per-tenant *capability configuration*: which subsystems and features a site sees (`events_enabled`, `subjects_enabled`, `analyzers_enabled`, `alerts_enabled`, …). These are durable product configuration, not transitional, so they're worth a typed, TMS-validated field. Fields on the `FeatureFlags` dataclass in [`das/utils/tenant/dataclass.py`](../../../das/utils/tenant/dataclass.py), deserialized from the `featureFlags` block. See [Typed feature flags](#typed-feature-flags).
- **Preview features** — short-lived rollout gates. Declared in an ER-side [registry](#preview-features) and read from a `previewFeatures` dict on the tenant payload; a [global override](#flipping-a-feature-on-for-everyone) lets you force one on (or off) for every tenant in a single ER change. The concept maps to the short-lived rollout category in [Martin Fowler's feature-toggle taxonomy](https://martinfowler.com/articles/feature-toggles.html): a **Preview Feature** keeps a latent feature dark in mainline, is flipped on as it rolls out, and is removed once the rollout is complete.
- **Gating Django admin pages** builds on a preview feature plus its global override — a single per-tenant gate, no separate Django-settings kill switch. See [Gating Django admin pages](#gating-django-admin-pages).

> For where a plain Django **setting** belongs (env-driven vs. Docker-only vs. test-only), see [Settings & Configuration](settings.md). Preview features are runtime gates; settings are deploy-time configuration.

> ## `features.tms.is_on()` — legacy, do not extend
>
> [`das/utils/features.py`](../../../das/utils/features.py) defines a tiny in-process flag registry whose only entry is `features.tms` (always `True`). It is a relic of the migration to the Tenant Management Service: code paths that needed to behave differently before vs. after TMS landed were gated on `features.tms.is_on()`. That migration is complete; **multi-tenancy is unconditional and `features.tms.is_on()` always returns `True`**.
>
> Existing call sites have not been ripped out — leaving them in place keeps diffs small and avoids surprises mid-flight. But:
>
> - **Do not add new `features.tms.is_on()` checks.** New code should assume TMS is on. If you find yourself wanting to branch on it, you don't.
> - **Do not extend the `Features` enum.** It is not a general-purpose flag system. For a new gate, use a [typed feature flag](#typed-feature-flags) or a [preview feature](#preview-features) as documented below.
> - When you happen to be modifying a function that contains a `features.tms.is_on()` check, you may inline the true branch and delete the import as a drive-by — but don't make it a separate task.

## Per-tenant flags from TMS

The Tenant Management Service ships two kinds of per-tenant flag to EarthRanger — typed feature flags and preview features. They are complementary, not old-vs-new; pick by longevity.

### Choosing where a new flag goes

| | Typed feature flag | Preview feature |
| --- | --- | --- |
| **Use for** | Durable per-site capability configuration — "what a site sees" (a subsystem on/off, an integration enabled) | A transitional gate that lets an unfinished feature ship dark and roll out gradually |
| **Lifespan** | Indefinite; part of the product's tenant-configuration surface | Temporary; **delete it once the feature is fully rolled out** |
| **Declared in** | `FeatureFlags` dataclass (`das/utils/tenant/dataclass.py`) | `PREVIEW_FEATURES` registry (`das/utils/tenant/preview_features.py`) |
| **Cost to add** | Two coordinated changes — ER dataclass **and** TMS schema | ER-only; no TMS schema change |
| **Typing** | Strongly typed and TMS-validated | Stringly-typed values in a generic dict |

The asymmetry is deliberate: a permanent capability flag is worth the coordinated, strongly-typed change, while a throwaway rollout gate shouldn't cost a TMS schema update. If you're unsure whether a flag will outlive its rollout, start it as a preview feature — promoting it to a typed flag later is cheaper than carrying a permanent stringly-typed entry.

### Typed feature flags

A long-lived set of flags live as fields on the [`FeatureFlags` dataclass in `das/utils/tenant/dataclass.py`](../../../das/utils/tenant/dataclass.py) and are deserialized from the `featureFlags` block of the TMS payload. They configure which capabilities a site sees, so we sometimes turn them off to simplify a given deployment. Access them via the tenant settings:

```python
from utils.tenant import get_tenant_settings

ts = get_tenant_settings()
if ts.feature_flags.alerts_enabled:
    ...
```

| Field | TMS field (`field_name`) | Default | Notes |
| --- | --- | --- | --- |
| `alerts_enabled` | `alertsEnabled` | `False` | Alerting subsystem |
| `buoy_api_enabled` | `buoyApiEnabled` | `False` | Buoy API |
| `daily_report_enabled` | `dailyReportEnabled` | `False` | Daily report generation |
| `kml_export` | `kmlExport` | `False` | KML export |
| `mapping_features_v2` | `mappingFeaturesV2` | `False` | Mapping features v2 |
| `tableau_enabled` | `tableauEnabled` | `False` | Tableau integration |
| `tableau_site_id` | `tableauSiteId` | `False` | Tableau site-id gating |
| `track_length` | `trackLength` | `False` | Track-length feature gating |
| `events_enabled` | `eventsEnabled` | `True` | Events subsystem |
| `subjects_enabled` | `subjectsEnabled` | `True` | Subjects subsystem |
| `spatial_features_enabled` | `spatialFeaturesEnabled` | `True` | Spatial features |
| `analyzers_enabled` | `analyzersEnabled` | `True` | Real-time analyzers |
| `require_idp` | `requireIdp` | `False` | Force IdP login for the tenant |
| `idp_org_id` | `idpOrgId` | `None` | Auth0 / IdP org identifier (string, not boolean) |

Adding one costs **two coordinated changes per flag** — a field on the ER dataclass and a matching field in the TMS schema. That cost is worth paying for a durable, strongly-typed capability flag; for a short-lived rollout gate, reach for a [preview feature](#preview-features) instead. (`idp_org_id` is the only non-boolean entry in the table — a configuration value rather than an on/off flag.)

### Preview features

Short-lived rollout gates are declared in a single ER-side registry — [`das/utils/tenant/preview_features.py`](../../../das/utils/tenant/preview_features.py) — and read from a generic `previewFeatures` dict on the tenant payload. Adding a preview feature is an **ER-only** change; TMS does not need a schema update.

```python
# das/utils/tenant/preview_features.py
PREVIEW_FEATURES: dict[str, PreviewFeature] = {
    "community_input_admin_enabled": PreviewFeature(
        default=False,
        description="Per-tenant gate for the Community Input Django admin page.",
    ),
    # ...new features go here
}
```

Read a feature with `get_preview_feature(name)`:

```python
from utils.tenant.preview_features import get_preview_feature

if get_preview_feature("community_input_admin_enabled"):
    ...
```

#### Resolution precedence

`get_preview_feature(name)` resolves a value in this order:

1. **`global_override`** — if the registered `PreviewFeature` sets `global_override` to a non-`None` value, that value wins for **every** tenant, regardless of what TMS sent. See [Flipping a feature on for everyone](#flipping-a-feature-on-for-everyone) below.
2. **Per-tenant value** — `get_tenant_settings().preview_features[name]` (the `previewFeatures` block on the wire), set through TMS without a release.
3. **`default`** — the registered fallback when the tenant hasn't set a value.

Other semantics:

- Asking for a feature name that isn't in `PREVIEW_FEATURES` raises `UnknownPreviewFeature`. This is intentional typo protection: every read site must correspond to a declared feature.
- A feature declared in code but not yet shipped by TMS will simply use its default — safe to merge ahead of TMS work.
- An operator who sets a value in TMS for a name that ER doesn't declare is silently ignored (the value lives in `preview_features` but no one reads it).

#### Setting a preview feature for a tenant (TMS API)

Per-tenant values — precedence level 2 above — live in the `previewFeatures` block of the tenant document and are set through the Tenant Management Service, with **no ER release**. Besides the TMS admin UI, you can set one directly with a `PATCH` against the TMS API:

```http
PATCH /v1.0/tenants/{tenant_id}?key={TMS_API_KEY}
Content-Type: application/json

{
  "previewFeatures": {
    "community_input_admin_enabled": true
  }
}
```

```bash
curl -X PATCH \
  "https://<tms-host>/v1.0/tenants/<tenant_id>?key=$TMS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"previewFeatures": {"community_input_admin_enabled": true}}'
```

- **TMS does not validate the keys.** Any string is accepted and stored — that's exactly what lets you gate a feature with a plain patch, ahead of (or without) any TMS schema change. The flip side is no typo protection on the TMS end: the key must match the name registered in `PREVIEW_FEATURES` exactly, or ER's `get_preview_feature` will never read it. Values must be booleans.
- **The patch merges.** `previewFeatures` is merged key-by-key with what's already stored, so setting one toggle leaves the others intact — you don't need to resend the whole dict. To turn a feature back off for a tenant, patch it to `false` rather than trying to remove the key.
- This is per-tenant. To turn a feature on for **every** tenant in one change, use a [`global_override`](#flipping-a-feature-on-for-everyone) instead.

#### Flipping a feature on for everyone

When you decide a gated feature should be visible to **all** tenants at once — e.g. making the Community Input admin public — set `global_override` on the registered `PreviewFeature` and ship it:

```python
"community_input_admin_enabled": PreviewFeature(
    default=False,
    global_override=True,   # now on for every tenant; per-tenant previewFeatures ignored
    description="...",
),
```

This is a one-line ER code change (PR + release) rather than touching `previewFeatures` on every tenant. `global_override=False` is the inverse — an emergency kill that forces the feature off everywhere even for tenants that opted in. Leave it `None` (the default) to defer to per-tenant values. There is no Django-settings kill switch in front of this — the preview feature is the single gate. Once a feature is fully and permanently rolled out, the right end state is to delete the feature and its checks, not to leave `global_override=True` forever.

### Adding a new preview feature

1. Add an entry to `PREVIEW_FEATURES` in `das/utils/tenant/preview_features.py` with a sensible default (almost always `False` — opt-in) and a one-line description.
2. Read it via `get_preview_feature("your_feature_name")` at the call site.
3. No TMS schema change required. Coordinate with TMS only to (a) ensure the TMS admin UI has a way to set values in the generic `previewFeatures` dict, and (b) flip the feature on for specific tenants when ready — see [Setting a preview feature for a tenant (TMS API)](#setting-a-preview-feature-for-a-tenant-tms-api).

### Enabling a preview feature in local development

In production the per-tenant values arrive in the tenant payload's `previewFeatures` block from TMS. Locally there's no TMS, so seed `preview_features` from your `das/.env` via the `PREVIEW_FEATURES` setting (parsed as JSON and applied by `DjangoSettingsTenantBuilder`):

```dotenv
# das/.env
PREVIEW_FEATURES={"community_input_admin_enabled": true}
```

This is the faithful local equivalent of TMS setting the feature for your tenant — it flows through the same `preview_features` → `get_preview_feature` path, so it honours [resolution precedence](#resolution-precedence) (a `global_override` in the registry still wins over it). It applies when the `DjangoSettingsClient` builds the tenant (`TMS_API_CLIENT=core.tms.DjangoSettingsClient`); if you instead run the `TestClient`, set the same key in `das/core/fixtures/tenant-response.json`'s `previewFeatures` block. Don't set `global_override`/`default` in the registry just to test locally — those are committed code.

## Gating Django admin pages

When you ship a new feature that includes a Django admin surface, gate the admin behind a single per-tenant preview feature so it can be merged early but stays dark by default. The feature's three-level [resolution precedence](#resolution-precedence) gives you everything the old two-layer scheme did, with one concept:

- **Merged but dark** — `default=False`, no `global_override`. The admin is registered but every `has_*_permission` returns `False`, so it's hidden from the index and inaccessible for all tenants (superusers included).
- **Early access for one tenant** — set `community_input_admin_enabled: true` in that tenant's `previewFeatures` via TMS. No release.
- **Public for everyone** — set `global_override=True` on the feature (one ER PR). See [Flipping a feature on for everyone](#flipping-a-feature-on-for-everyone).

The API for the feature is *not* gated by this scheme — ship it independently. That's the point of the design: the API can be public while the Django admin stays hidden until you flip the feature.

> **No import-time kill switch.** Earlier revisions paired this with an `AdminFeatureFlag(model, flag="<FEATURE>_ADMIN_ENABLED")` decorator that read a Django setting and *unregistered* the model at import time. That layer has been removed for admin gating — the preview feature is the single source of truth. (`AdminFeatureFlag` itself still exists in `das/core/common.py` for feature-wide settings like `PATROL_ENABLED`; don't use it for new admin-only gates.)

### Pattern

Add the `PreviewFeatureAdminMixin` (`das/core/common.py`) to the `ModelAdmin` and set `preview_feature` to the name of an entry in `PREVIEW_FEATURES`.

```python
from core.common import PreviewFeatureAdminMixin

@admin.register(models.CommunityInput)
class CommunityInputAdmin(PreviewFeatureAdminMixin, ModelAdminDisplayingManyToManyFieldMixin):
    preview_feature = "community_input_admin_enabled"
    ...
```

`PreviewFeatureAdminMixin` overrides `has_module_permission` / `has_view_permission` / `has_add_permission` / `has_change_permission` / `has_delete_permission` to consult `get_preview_feature(<preview_feature>)` at request time. A typo'd name raises `UnknownPreviewFeature` at the first request that hits the admin, surfacing the mistake immediately.

### Naming convention

| Where | Name |
| --- | --- |
| `PREVIEW_FEATURES` registry in `utils/tenant/preview_features.py` | `<feature>_admin_enabled` (sent on the wire as the same key inside `previewFeatures`) |

The `_admin_enabled` suffix distinguishes admin-only gates from feature-wide settings like `PATROL_ENABLED` that affect more than the admin.

### Steps to add a gate

1. Register `<feature>_admin_enabled` in `PREVIEW_FEATURES` (`das/utils/tenant/preview_features.py`) with `default=False` and a one-line description.
2. Add `PreviewFeatureAdminMixin` to the `ModelAdmin` and set `preview_feature = "<feature>_admin_enabled"` as shown above.
3. Enable per tenant by setting the feature in `previewFeatures` via TMS (no release — see [Setting a preview feature for a tenant (TMS API)](#setting-a-preview-feature-for-a-tenant-tms-api)), or for everyone by setting `global_override=True` on the feature (one ER PR). No TMS schema change is required either way.

## Limitations

Neither mechanism supports per-user gating or staged percentage rollouts. Both the typed flags and preview features are loaded once per request via `get_tenant_settings()`, so a value cannot vary mid-request, and a `global_override` change ships with an ER release. For anything user-scoped, use permissions; for staged percentage rollouts, reach for a dedicated remote flag service rather than extending the patterns here.
