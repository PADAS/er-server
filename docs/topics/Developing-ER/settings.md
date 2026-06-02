# Settings & Configuration

EarthRanger's Django configuration is layered. Knowing which file a setting belongs in is the difference between a value that's configurable in production and one that silently can't be changed without a code release. This page is the single source of truth for **where a new setting goes**; for runtime feature toggles (per-tenant flags, admin kill switches) see [Feature Flags](feature-flags.md).

## The settings files

| File | Purpose |
| --- | --- |
| [`das/das_server/settings.py`](../../../das/das_server/settings.py) | Base settings, **and the home for all environment-driven settings**. Reads env vars via `env.bool(...)` / `env.str(...)` / `env.int(...)` — `env` is configured at the top of the file from [`django-environ`](https://django-environ.readthedocs.io/). |
| [`das/das_server/local_settings_docker.py`](../../../das/das_server/local_settings_docker.py) | Overrides specific to the Kubernetes production / Docker-compose environment that are **not** driven by env vars. Predates the project's `django-environ` adoption and is **not** the default home for new settings. |
| [`das/test_scripts/unittest_settings.py`](../../../das/test_scripts/unittest_settings.py) | Test-only overrides. Imports `local_settings_docker` first, then forces specific values needed for the test suite. |
| `.env` (project root, git-ignored) | Local-development environment variables. `django-environ` loads it automatically via `environ.Env.read_env(...)`. |

`DJANGO_SETTINGS_MODULE` selects which module is active; `DEBUG` / `DEV` toggle development mode.

## Where does my new setting go?

- **Configurable from the environment (12-factor)** → `settings.py` with `env.bool("MY_SETTING", <default>)`.
- **A fixed, hardcoded default that callers never override at runtime** → `settings.py` as `MY_SETTING = <value>`.
- **Different value under Kubernetes/Docker than in dev, and not exposed as an env var** → `local_settings_docker.py`.
- **A forced value needed only for the test suite to pass** → `test_scripts/unittest_settings.py`.

### One source of truth per setting

Do **not** declare the same setting in both `settings.py` and `local_settings_docker.py`. That was the old pre-`django-environ` workaround and it creates two sources of truth. Some older settings (e.g. `PATROL_ENABLED`) still live in `local_settings_docker.py` for historical reasons — **do not treat them as precedent.** New env-driven settings go in `settings.py`.

### Example

```python
# das_server/settings.py
ENABLE_SILK = env.bool("ENABLE_SILK", False)          # env-driven, defaults off

# test_scripts/unittest_settings.py
ENABLE_SILK = False                                    # forced off for the test suite
```

## Tenant-scoped settings, caches, and querysets

A handful of settings-adjacent concerns are tenant-aware and have their own rules — read [Multi-Tenancy](multi-tenancy.md) before working in these areas:

- **Tenant-scoped querysets in admin/form classes** must be rebuilt per-request (in `__init__` / `get_queryset` / `formfield_for_*`), never declared with a live tenant-scoped queryset at class/import time.
- **Cache aliases** configured with `KEY_FUNCTION: utils.tenant.cache.make_cache_key` automatically prefix every key with the thread-local tenant ID — do not add an explicit `tenant_id` to the key yourself.

## See also

- [Feature Flags](feature-flags.md) — runtime toggles: per-tenant release toggles, the registry, and the global override used to gate Django admin pages. (Toggles are *not* Django settings — that page explains why.)
- [Multi-Tenancy](multi-tenancy.md) — tenant isolation, threadlocal tenant context, and tenant-scoped caches.
