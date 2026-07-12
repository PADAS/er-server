# AGENTS.md
---
description:
globs:
alwaysApply: true
---

## Project Overview

EarthRanger (DAS - Domain Awareness System) is a Django-based web application for wildlife conservation and domain awareness. This is a multi-tenant system that tracks wildlife, manages events, handles patrols, and provides real-time monitoring capabilities.

## Architecture Overview

[Architecture Documentation](docs/architecture/architecture-overview.md)

## Module Boundaries

### `utils/` must stay app-agnostic

Code in `das/utils/` must not reference or assume any specific app or domain concept from this project (e.g. patrols, events, subjects, sources, observations, reports, tenants). A util should be conceptually extractable as a standalone Python library with no EarthRanger-specific imports, model references, or vocabulary.

- If a helper needs to know about a patrol, event, subject, etc., it belongs in that app (e.g. `activity/`, `observations/`), not in `utils/`.
- For generic infrastructure (throttling, caching, retries, rate limiting, batching), parameterize on generic keys/types — do not hard-code app-specific model names, signal handlers, or business rules.
- `utils/tenant` predates this rule and is a known violation. Do not treat it as precedent or extend the pattern; new domain-aware code goes in the owning app.

When in doubt, ask: "Could I lift this file into a separate Python package and `pip install` it from another project?" If the answer is no, it does not belong in `utils/`.

## Multi-Tenant Architecture

This system is multi-tenant aware. Most models have a `das_tenant` field that isolates data between tenants.

Key considerations:

- Data isolation at the database level
- Tenant context in requests and background tasks
- Tenant-specific configurations and permissions
- Cross-tenant queries require special authorization

### Tenant-scoped querysets in admin/form classes

Class-level `queryset=` declarations on `ModelChoiceField` / `ModelMultipleChoiceField` (and on `ModelAdmin` attributes that take a queryset) are evaluated **at import time**, before any request — and therefore before the tenant middleware has set the threadlocal. For tenant-scoped models (`User`, `PermissionSet`, `Subject`, anything inheriting `TenantModelMixin`), that import-time evaluation either raises `TenantNotFoundInLocalThreadException` or — worse — silently captures whatever tenant happens to be active during import (tests, management commands, the first request to land on a worker).

The pattern in this codebase is:

- Declare the field with a placeholder queryset at class scope so Django's form/admin machinery is satisfied.
- **Reassign the queryset in `__init__` (forms) or `get_queryset` / `formfield_for_*` (admins)** so it is rebuilt per-request, with `get_tenant_settings()` resolving inside the request scope.

Example: `accounts/forms.py:PermissionSetAdminForm` declares `User.objects.all()` and `PermissionSet.objects.all()` at class scope, then re-assigns both in `__init__`. Do not "clean up" those reassignments — they look redundant but are load-bearing.

When you reassign a M2M queryset in `__init__`, you also drop any `select_related` / `prefetch_related` that the parent `ModelAdmin.formfield_for_manytomany` had added. If the related model's `__str__` touches a foreign key (e.g. `Permission.__str__` reads `content_type`), reapply the hint yourself or you'll re-introduce N+1s during widget rendering.

### Tenant-scoped cache and lock keys

Cache aliases configured with `KEY_FUNCTION: utils.tenant.cache.make_cache_key` (see `das_server/settings.py`) automatically prefix every key with the thread-local tenant ID. This applies to:

- `cache.get` / `cache.set` / `cache.delete` — keys are transformed before reaching the backend.
- `cache.lock(key, ...)` on `django-redis` — the lock key goes through the same `make_key` pipeline, so distributed locks are tenant-isolated by default.

When reviewing or writing code that uses one of these cache aliases, **do not add an explicit `tenant_id` to the key string** — it would double-prefix at the backend. Trust the `KEY_FUNCTION`. Only build a tenant-prefixed key by hand when bypassing the configured cache (e.g. talking to a raw `redis.Redis` client like `MultitenantRedisClient`, where the prefix is applied by the wrapper, not by you).

### Data migrations that iterate tenant-scoped or revision models

In a `RunPython` data migration, `apps.get_model(...)` returns **historical `__fake__` models**. Under django-multitenant (4.1.1), **constructing** an instance of a historical `TenantModel` whose tenant config (`TenantMeta` / `tenant_id`) did not survive state rendering raises `AttributeError: apps.get_model method should not be used to get the model <X>`. The error triggers on **iteration** (`list(Model.objects...)`, `for row in qs`), **not** on building the queryset — so a migration can look fine until the rows are materialized.

This is **model-specific and not predictable**: `EventType` survives (it keeps a `TenantMeta`), but `DASTenant` and the dynamically generated `*Revision` models (e.g. `EventTypeRevision`) do **not**.

Patterns to use:

- **A model you must iterate whose historical version crashes** (e.g. `DASTenant`): import the **live** model directly (`from core.models.core import DASTenant`). This is intentional and load-bearing — do not "clean it up" to `apps.get_model`.
- **A revision / `*Revision` model you only need to read**: query with `.values_list(..., named=True)` (or `.values()`) so **no model instance is constructed** (named `Row` tuples satisfy duck-typed consumers). See `activity/schemas/ops/revision_history.py::fetch_in_migration`.
- **Wrap tenant-scoped queries** in `UnsetDASTenantContextManager()` and **materialize** (`list(...)`) the result **inside** that context — do not return a lazy queryset that gets evaluated after the context exits.

**Testing**: drive the `RunPython` body with the **historical app-state** — `MigrationExecutor(connection).loader.project_state((app_label, parent_migration)).apps` — **not** the live `django.apps.apps`. The live registry hides this class of bug because live models keep their tenant attributes. (Reference example: `activity/tests/test_repair_upstream_integration.py`.)

The above covers the **read** side. The **write** side has its own landmine — see "Writes under unset/absent tenant context" immediately below.

### Writes under unset/absent tenant context

Tenant scoping protects *reads*; it does **not** touch the implicit `WHERE` clause of a *write*. Seeded/global tenant-scoped rows — `EventType`, `EventCategory`, `EventClass`, `EventFactor`, `TileLayer`, and similar — **reuse the same `id` (UUID) across every tenant**. In production (AlloyDB) the physical primary key is the composite `(das_tenant_id, id)`, even though Django models `id` as the sole PK, which is why duplicate `id`s coexist. So an ORM `instance.save(update_fields=[…])` or `QuerySet.update(…)` — which key the write on `id` alone — will, when the tenant context is **unset or absent** (data migrations, management commands, shells, anything inside `UnsetDASTenantContextManager`), emit `UPDATE … WHERE id=<uuid>` with no tenant predicate and **overwrite every tenant's row sharing that id**.

Iterating per-tenant and scoping your *reads* (`.filter(das_tenant_id=…)`) does not help — the danger is entirely in the write. This is exactly how `activity/migrations/0198_fix_v2_link_fields` and `0203_repair_v2_collection_schemas` clobbered V2 `EventType` schemas fleet-wide (prod incident 2026-06-29): both scope the read correctly, then `event_type.save(update_fields=["schema","updated_at"])` inside `UnsetDASTenantContextManager`. Those two writes now carry a warning comment — do not copy the pattern.

When writing with no tenant in context, do one of:

- **Set the context around the write** (preferred): `with TenantContextManager(domain=tenant.domain): event_type.save(...)`. django-multitenant then injects `das_tenant_id` into the `UPDATE`. This is what the safe per-tenant migrations do (`0064`, `0175`, `0184`, `mapping/0072`). Note `UnsetDASTenantContextManager` is the *opposite* — it strips the scoping and must not wrap a write to a shared-PK model.
- **Name the tenant in the write's `WHERE` yourself**: `Model.objects.filter(id=pk, das_tenant_id=tid).update(...)`, or raw SQL `UPDATE … WHERE id=%s AND das_tenant_id=%s`. Raw SQL is not ORM-tenant-scoped, so it is safe here **only** because you supply the predicate.

An intentional fleet-wide write (e.g. `accounts/migrations/0062` setting an `is_system` flag by username across all tenants) is acceptable **only** when it sets a tenant-independent value and cannot overwrite one tenant's data with another's — say so in a comment so reviewers don't read it as this bug.

## Dynamic schemas (`das/schemas/`)

`DynamicSchemaFromSourceView` emits choice fields in two interchangeable shapes — **`enum` + `x-enumExtra`** (default) and **`oneOf`** — picked per request via `?s_format`, per subclass via `default_format`, or per call site via `schemas.format_serializers.output_format_override(...)`.

Landmines (full guidance: [.cursor/rules/das-dynamic-schemas.mdc](.cursor/rules/das-dynamic-schemas.mdc)):

- Internal consumers that can only understand one shape (currently `AlertingSchemaPropertiesAdapter._process_v2_schema` and `V2SchemaAdapter._ensure_rendered`) wrap their `EventTypeSchemaService.get_rendered_schema(...)` call in `output_format_override(OUTPUT_FORMAT_ONE_OF)`. Never wrap the service itself — it serves the public API too.
- `_CHOICE_MARKERS` in `activity/alerting/businessrules.py` accepts `enumNames`, `x-enumExtra`, `anyOf`, `oneOf`. **Do not add bare `enum`** — a V1 `{"type":"string","enum":[…]}` without `enumNames` is a string-validation constraint, not a choice; reclassifying it drops `equal_to` / `contains` and breaks existing alert rules.
- Invalid request input (e.g. `?s_format=bogus`) must raise `rest_framework.exceptions.ValidationError` (→ 400). Plain `ValueError` becomes a 500 because `utils/drf.api_exception_handler` only maps DRF `APIException` to 4xx. Plain `ValueError` is fine inside helpers where a 500 *is* the right signal (programmer-input validation).
- OpenAPI: use `schemas.spectacular_extensions.JSON_SCHEMA_TYPES` wherever JSON Schema `type` values are listed — single source of truth for the `s_type` query enum and the response `type` field.

## Configuration

### Settings Structure

- `das_server/settings.py` - Base settings, **and the home for all environment-driven settings**. Read env vars here via `env.bool(...)` / `env.str(...)` / `env.int(...)` (`env` is already configured at the top of the file from `django-environ`).
- `das_server/local_settings_docker.py` - Reserved for overrides specific to the Kubernetes production / Docker-compose environment that are **not** driven by env vars. This file predates the project's `django-environ` adoption and is not the default home for new settings. Some older entries (e.g. `PATROL_ENABLED = env.bool("PATROL_ENABLED", True)`) still live here for historical reasons; do not treat them as precedent.
- `test_scripts/unittest_settings.py` - Test-only overrides (imports `local_settings_docker` first and then forces specific values needed for the test suite).
- Environment variables for local development go in a `.env` file at the project root; `django-environ` loads it automatically.

#### Where does my new setting go?

- **Configurable from the environment (12-factor)** → `settings.py` with `env.bool("MY_SETTING", <default>)`.
- **A fixed, hardcoded default that callers never override at runtime** → `settings.py` as `MY_SETTING = <value>`.
- **Different value when running under Kubernetes/Docker than in dev, and not exposed as an env var** → `local_settings_docker.py`.
- **Forced value needed only for the test suite to pass** → `test_scripts/unittest_settings.py`.

Do not declare the same setting in both `settings.py` and `local_settings_docker.py` — that was the old pre-`django-environ` workaround and creates two sources of truth.

## Python Style & Conventions

- Follow PEP 8 for formatting. pre-commit handles import sorting and pruning, so don't waste time managing whitespace and other code formatting.
- Use Python typing `Protocol` and not ABC for defining abstract classes. Rely on the type checker to enforce all required methods are implemented.

### Dates and timezones

- Do **not** use `pytz` in new code — it has been removed from the project. Use the stdlib `datetime`/`zoneinfo` instead.
- Construct UTC datetimes with `datetime.now(tz=timezone.utc)` or `datetime(..., tzinfo=timezone.utc)`. Do not use `datetime.utcnow()` (returns a naive datetime).
- For non-UTC zones, use `zoneinfo.ZoneInfo("Region/City")` rather than `pytz.timezone(...)`.
- In Django code, prefer `django.utils.timezone.now()` for "current time, tenant-aware" and reserve stdlib `datetime.now(tz=...)` for non-Django utilities and tests.
- Never call `pytz.utc.localize(naive_dt)` — replace with `naive_dt.replace(tzinfo=timezone.utc)` or, better, construct the datetime aware in the first place.

## Django/Python Conventions

- Define API query-parameter filtering using DRF `BaseFilterBackend` and the `django-filter` library.
- Use test-driven design principles. When fixing bugs, write the assertion unit test that exposes the bug, then fix the code to pass the test.
- Write API documentation in markdown for new or updated APIs; documentation is stored in `/docs`.

## Python Type Annotations

All code must be fully type-annotated. Use mypy (strict mode) or pyright to validate.

- Use `from __future__ import annotations` at the top of every module to enable postponed evaluation.
- Never use `Any` unless absolutely unavoidable — document why with a comment.

## Testing with pytest

Pytest conventions (test structure, fixtures, parametrize) live in the `er-developer:core-testing` skill, which auto-triggers when writing or modifying tests. Two rules worth keeping in view: organize a group of unit test functions in a class, and name tests as descriptive sentences (`test_returns_none_when_user_not_found`, not `test_user_2`).

## What Agents Should Never Do

- Do not suppress type errors with `# type: ignore` without an explanatory comment.
- Do not write tests that pass or use `...` as placeholders — incomplete tests must be marked `@pytest.mark.skip(reason="...")`.
- Do not commit code with failing tests or type errors.
- Do not add dependencies without updating `pyproject.toml`.
- Do not use `print()` for logging — use the `logging` module.
- Do not put app-specific code (patrols, events, subjects, sources, tenants, etc.) in `das/utils/`. See "Module Boundaries" — utils must be domain-agnostic.

## Specialized Agents

For implementation work, use the specialized agents in `.claude/agents/`:

- `backend-developer` - Django development, database operations, testing
- `frontend-developer` - React development, Playwright E2E tests
- `code-reviewer` - Code review for quality, security, performance, multi-tenancy
