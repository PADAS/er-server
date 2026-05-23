# Feature Flags

EarthRanger has two gating mechanisms you should reach for in new code, plus one legacy artifact you should leave alone:

- **Per-tenant flags** in the `FeatureFlags` dataclass in [`das/utils/tenant/dataclass.py`](../../../das/utils/tenant/dataclass.py) — values supplied by the Tenant Management Service that differ per tenant. Covered in [Per-tenant flags from TMS](#per-tenant-flags-from-tms).
- **Django settings + the `AdminFeatureFlag` decorator** — a deploy-time kill switch read from `django.conf.settings`. Same value for every tenant on the process. Used for gating Django admin pages alongside the per-tenant flag above; see [Gating Django admin pages](#gating-django-admin-pages).

> ## `features.tms.is_on()` — legacy, do not extend
>
> [`das/utils/features.py`](../../../das/utils/features.py) defines a tiny in-process flag registry whose only entry is `features.tms` (always `True`). It is a relic of the migration to the Tenant Management Service: code paths that needed to behave differently before vs. after TMS landed were gated on `features.tms.is_on()`. That migration is complete; **multi-tenancy is unconditional and `features.tms.is_on()` always returns `True`**.
>
> Existing call sites have not been ripped out — leaving them in place keeps diffs small and avoids surprises mid-flight. But:
>
> - **Do not add new `features.tms.is_on()` checks.** New code should assume TMS is on. If you find yourself wanting to branch on it, you don't.
> - **Do not extend the `Features` enum.** It is not a general-purpose flag system. For a new toggle, use per-tenant flags (TMS) or `AdminFeatureFlag` (Django setting) as documented below.
> - When you happen to be modifying a function that contains a `features.tms.is_on()` check, you may inline the true branch and delete the import as a drive-by — but don't make it a separate task.

## Per-tenant flags from TMS

The `FeatureFlags` dataclass in [`das/utils/tenant/dataclass.py`](../../../das/utils/tenant/dataclass.py) models the `featureFlags` payload returned by the Tenant Management Service for the current tenant, and is populated per-tenant when tenant settings are loaded.

Access these via the tenant settings:

```python
from utils.tenant import get_tenant_settings

ts = get_tenant_settings()
if ts.feature_flags.alerts_enabled:
    ...
```

The current schema and defaults are hardcoded in the `FeatureFlags` dataclass and look like this. Defaults are used when TMS does not supply a value; tenants override them via TMS.

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
| `community_input_admin_enabled` | `communityInputAdminEnabled` | `False` | Per-tenant gate for the Community Input Django admin page. Used together with the `COMMUNITY_INPUT_ADMIN_ENABLED` Django setting — see [Gating Django admin pages](#gating-django-admin-pages). |

When adding, removing, or renaming a per-tenant flag:

1. Update the `FeatureFlags` dataclass in `das/utils/tenant/dataclass.py` and the table above. The Python attribute name and the `field_name` (camelCase, used on the wire to TMS) must both be set.
2. Coordinate with the Tenant Management Service so the new field is recognised and persisted. A flag that the dataclass knows about but TMS does not will always fall back to its default; a flag TMS sends but the dataclass does not declare is silently dropped on decode.
3. Pick a sensible default — most existing flags default to `False` (opt-in), with subsystems that are universally on (`events_enabled`, `subjects_enabled`, `spatial_features_enabled`, `analyzers_enabled`) defaulting to `True`.

`idp_org_id` is the only non-boolean entry; it is included here because it lives on the `FeatureFlags` payload, but it is a configuration value rather than a toggle.

## Gating Django admin pages

When you ship a new feature that includes a Django admin surface, gate the admin behind **two layers** so it can be merged early but stays dark by default:

1. **Global kill switch** — a Django setting checked at import time. Defaults `False`, so newly-merged admin code is invisible on every deploy until explicitly enabled.
2. **Per-tenant gate** — a flag on the `FeatureFlags` dataclass checked at request time. Lets you flip individual tenants on once the global switch is enabled in their environment.

Both layers default off. With both off, nothing changes for users. The API for the feature is *not* gated by this scheme — ship it independently.

### Pattern

Use the existing `AdminFeatureFlag` decorator (`das/core/common.py`) for layer 1 and the `TenantFeatureFlaggedAdminMixin` (same module) for layer 2.

```python
from core.common import AdminFeatureFlag, TenantFeatureFlaggedAdminMixin

@AdminFeatureFlag(models.CommunityInput, flag="COMMUNITY_INPUT_ADMIN_ENABLED")
@admin.register(models.CommunityInput)
class CommunityInputAdmin(TenantFeatureFlaggedAdminMixin, ModelAdminDisplayingManyToManyFieldMixin):
    tenant_feature_flag = "community_input_admin_enabled"
    ...
```

Decorator order matters: `admin.register` (bottom) runs first and registers the admin; `AdminFeatureFlag` (top) runs second and *unregisters* the model if the Django setting is False, so the admin URLs never exist.

When `AdminFeatureFlag` allows the admin through, `TenantFeatureFlaggedAdminMixin` overrides `has_module_permission` / `has_view_permission` / `has_add_permission` / `has_change_permission` / `has_delete_permission` to consult `get_tenant_settings().feature_flags.<tenant_feature_flag>`. A missing field on the dataclass falls through to `False`, so a flag declared in code before TMS knows about it is dark by default.

### Naming convention

| Layer | Where | Name |
| --- | --- | --- |
| Global Django setting | `das_server/settings.py` (env-driven), `unittest_settings.py` (force-on for tests) | `<FEATURE>_ADMIN_ENABLED` (e.g. `COMMUNITY_INPUT_ADMIN_ENABLED`) |
| Per-tenant flag | `FeatureFlags` dataclass in `utils/tenant/dataclass.py` | `<feature>_admin_enabled` with `field_name="<feature>AdminEnabled"` |

The `_ADMIN_ENABLED` suffix distinguishes admin-only gates from feature-wide settings like `PATROL_ENABLED` that affect more than the admin.

> **Where to put env-driven settings.** Anything controlled by an environment variable goes in `das_server/settings.py` via `env.bool(...)` / `env.str(...)` / etc. `local_settings_docker.py` is reserved for overrides that are specific to the Kubernetes production environment and never read from an env var — it predates this codebase's `django-environ` adoption and is not the default home for `env.bool(...)` calls. Some older settings (e.g. `PATROL_ENABLED`) still live in `local_settings_docker.py`; do not use them as precedent.

### Steps to add a gate

1. Add `<FEATURE>_ADMIN_ENABLED = env.bool("<FEATURE>_ADMIN_ENABLED", False)` to `das/das_server/settings.py`.
2. Set `<FEATURE>_ADMIN_ENABLED = True` in `das/test_scripts/unittest_settings.py` if the admin already has tests.
3. Add `<feature>_admin_enabled` to the `FeatureFlags` dataclass with `default=False` and the matching table row in this document.
4. Decorate the `ModelAdmin` as shown above and add the mixin.
5. Coordinate with the Tenant Management Service team so the new `<feature>AdminEnabled` field is recognised. Until that lands, every tenant stays dark.

## Limitations

Neither mechanism supports per-user gating or staged percentage rollouts. The Django settings layer requires a process restart to change. The per-tenant layer can be updated through TMS without a restart, but the value is loaded once per request via `get_tenant_settings()` — it cannot vary mid-request. For anything user-scoped, use permissions; for staged rollouts, reach for a dedicated remote flag service rather than extending the patterns here.
