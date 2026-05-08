# Plan for the upgrade to Django 4.2

Here we want to outline the changes necessary to upgrade our project from Django 3.2 to 4.2.
Once we identify the tasks and answer any questions, we will perform the tasks.

**Reference**: [Django 4.2 release notes](https://docs.djangoproject.com/en/6.0/releases/4.2/)
[ERA-11444 Migrate to the latest version of Django we can (4.2)](https://allenai.atlassian.net/browse/ERA-11444)

---

## Phase 1: CRITICAL -- Will Break Immediately

These changes **must** be made before the application can start on Django 4.2.

### 1.1 Update Django version pin

- **File**: `pyproject.toml:30`
- **Change**: `django==3.2.25` -> `django==4.2.x` (latest 4.2 LTS)

### 1.2 Fix URL imports (6 files)

`re_path` and `include` were removed from `django.conf.urls` in Django 4.0. Must import from `django.urls`.

| File | Current Import | Fix |
|------|---------------|-----|
| `das/das_server/urls.py:22` | `from django.conf.urls import include` | `from django.urls import include` |
| `das/reports/urls.py:16` | `from django.conf.urls import re_path` | `from django.urls import re_path` |
| `das/activity/urls.py:1` | `from django.conf.urls import re_path` | `from django.urls import re_path` |
| `das/accounts/urls.py:16` | `from django.conf.urls import re_path` | `from django.urls import re_path` |
| `das/accounts/admin.py:17` | `from django.conf.urls import re_path` | `from django.urls import re_path` |
| `das/choices/urls.py:1` | `from django.conf.urls import re_path` | `from django.urls import re_path` |
| `das/buoy/urls.py:1` | `from django.conf.urls import re_path` | `from django.urls import re_path` |

### 1.3 Fix 73 migration files referencing removed JSONField path

`django.contrib.postgres.fields.jsonb.JSONField` was removed in Django 4.0. All 73 migration files referencing it will fail to import.

- **Affected apps**: `accounts`, `activity`, `analyzers`, `mapping`, `observations`, `tracking`, `usercontent`
- **Fix**: Change `django.contrib.postgres.fields.jsonb.JSONField` -> `django.db.models.JSONField` in all affected migration files
- **Alternative**: Squash migrations to eliminate old references

### 1.4 Remove `NullBooleanField` usage (removed in Django 4.0)

- **File**: `das/observations/forms.py:163`
- **Current**: `two_way_messaging = forms.NullBooleanField(...)`
- **Fix**: Replace with `forms.BooleanField(required=False)` with an appropriate widget, or use `BooleanField` with a `Select` widget providing None/True/False choices

### 1.5 Fix `CSRF_TRUSTED_ORIGINS` format (Django 4.0 requires scheme)

- **File**: `das/das_server/local_settings_docker.py:90` -- `CSRF_TRUSTED_ORIGINS = list(SERVER_NAMES)` uses bare domains without `https://`
- **File**: `das/utils/tenant/domains.py:36` -- `settings.CSRF_TRUSTED_ORIGINS.extend(new_tenant_domains)` appends bare domains
- **Fix**: Prepend `https://` to all values in `CSRF_TRUSTED_ORIGINS`

### 1.6 Upgrade third-party packages

These packages need version bumps for Django 4.2 compatibility:

| Package | Current Version | Action |
|---------|----------------|--------|
| `django-multitenant` | 3.2.1 | Upgrade (version targets Django 3.2) |
| `django-pgviews` | 0.5.7 | Upgrade or find alternative (last release 2020) |
| `django-leaflet` | 0.31.0 | Upgrade to >=0.33 |
| `django-mptt` | 0.14.0 | Upgrade to >=0.16 |
| `django-storages[google]` | 1.13.2 | Upgrade to >=1.14 |
| `whitenoise` | 5.3.0 | Upgrade to >=6.0 |
| `django-bitfield` | 2.2.0 | Verify Django 4.2 support |
| `django-docs` | 0.3.3 | Verify Django 4.2 support |
| `django-sendsms` | 0.5 | Verify Django 4.2 support |
| `django-tagulous` | 1.3.3 | Verify Django 4.2 support |
| `django-fast-update` | 0.2.4 | Verify Django 4.2 support |
| `django-readonly-field` | 1.1.2 | Verify Django 4.2 support |

Risks to watch during testing:
  - django-bitfield (2.2.0) - unmaintained, may not work with Django 4.2
  - django-tagulous 1.x -> 2.x - major version bump, possible API changes
  - django-multitenant 3.x -> 4.x - major version bump, test thoroughly
  - django-sendsms (0.5) - appears abandoned

**Already compatible** (no changes needed): `djangorestframework==3.15.1`, `django-filter==23.5`, `django-oauth-toolkit==2.3.0`, `django-cors-headers==4.4.0`, `django-debug-toolbar==4.3.0`, `django-versatileimagefield==3.1`

---

## Phase 2: HIGH PRIORITY -- Behavioral Changes & Deprecation Warnings

These won't prevent startup but may cause runtime bugs or emit deprecation warnings.

### 2.1 Migrate `DEFAULT_FILE_STORAGE` to `STORAGES` setting (deprecated in 4.2)

| File | Current |
|------|---------|
| `das/das_server/local_settings_docker.py:133` | `DEFAULT_FILE_STORAGE = "core.storages.TenantGoogleCloudStorage"` |
| `das/test_scripts/unittest_settings.py:10` | `DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"` |
| `das/analyzers/tests/test_geofencing.py:46` | `@override_settings(DEFAULT_FILE_STORAGE=...)` |
| `.env.template:55` | `DEFAULT_FILE_STORAGE=...` |

**Fix**: Migrate to new `STORAGES` dict format:
```python
STORAGES = {
    "default": {
        "BACKEND": "core.storages.TenantGoogleCloudStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```
Note: The old setting still works as a transitional alias in 4.2 but will be removed in 5.0.

### 2.2 Migrate `pytz` usage to `zoneinfo` (80+ files)

Django 4.0+ uses `zoneinfo` instead of `pytz` by default. While `pytz` still works, mixing `pytz` and `zoneinfo` timezone objects can cause subtle DST bugs.

**Key non-test files**:
- `das/utils/middleware.py:10`
- `das/utils/date.py:7`
- `das/core/forms_utils.py:3`
- `das/observations/models.py:28`
- `das/observations/views/__init__.py:9`
- `das/activity/models.py:11`
- `das/activity/views/events/base.py:10`
- `das/usercontent/models.py:5`
- Plus 70+ more files (tracking plugins, analyzers, sensors, serializers)

**Common replacements**:
| Old (pytz) | New (zoneinfo) |
|------------|----------------|
| `import pytz` | `from zoneinfo import ZoneInfo` |
| `pytz.utc` | `datetime.timezone.utc` |
| `pytz.timezone("US/Eastern")` | `ZoneInfo("US/Eastern")` |
| `pytz.utc.localize(dt)` | `dt.replace(tzinfo=datetime.timezone.utc)` |

**Transitional option**: Set `USE_DEPRECATED_PYTZ = True` in settings to keep pytz behavior through Django 4.x while migrating incrementally.

### 2.3 Convert `index_together` to `Meta.indexes` (deprecated in 4.2)

- **File**: `das/observations/models.py:3122-3125`
- **Current**:
  ```python
  index_together = [
      ("das_tenant", "sender_id", "message_time"),
      ("das_tenant", "receiver_id", "message_time"),
  ]
  ```
- **Fix**: Convert to `Meta.indexes`:
  ```python
  indexes = [
      models.Index(fields=["das_tenant", "sender_id", "message_time"]),
      models.Index(fields=["das_tenant", "receiver_id", "message_time"]),
  ]
  ```
- Migration files with `index_together` can remain as-is (they record history). A new migration must be created.

### 2.4 Test custom database backend

- **File**: `das/utils/db/backends/postgis/base.py`
- Contains overridden `_alter_field` and `_create_fk_sql` methods whose signatures may have changed between 3.2 and 4.2
- Contains dead code: `if django.VERSION < (3, 0):` check at line 126
- **Action**: Carefully test against Django 4.2. Method signatures for `DatabaseSchemaEditor` changed across versions.

### 2.5 New `SECURE_CROSS_ORIGIN_OPENER_POLICY` default (Django 4.0)

- Django 4.0 sets `SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'` by default
- This adds a `Cross-Origin-Opener-Policy: same-origin` header
- **Action**: Verify this doesn't break any popup/OAuth flows. Set to `None` if needed.

### 2.6 `Model.save()` with `update_or_create()` now passes `update_fields` (Django 4.2)

- Any custom `save()` methods that don't expect or handle `update_fields` may silently skip saving some fields when called via `update_or_create()`
- **Action**: Audit all custom `save()` methods in models

Key follow-up items from the audits:

  1. 9 models with at-risk save() methods — Patrol.save() is highest risk. These should
  be updated to follow the Event.save() pattern (add extra fields to update_fields
  before calling super().save()).


### 2.7 Fix `handler404` assignment

- **File**: `das/das_server/urls.py:86`
- **Current**: `django.conf.urls.handler404 = "utils.drf.error404View"`
- **Fix**: Change to module-level `handler404 = "utils.drf.error404View"`

---

## Phase 3: LOW PRIORITY -- Cleanup & Future-Proofing

### 3.1 Remove `TEMPLATE_DEBUG` setting (no effect in 4.0+)

- **File**: `das/das_server/local_settings_docker.py:40`
- **Action**: Remove `TEMPLATE_DEBUG = env.bool("ENABLE_DEBUG", False)`

### 3.2 Remove `USE_L10N = True` (now the default)

- **File**: `das/das_server/settings.py:252`
- **Action**: Remove (defaults to `True` since Django 4.0, deprecated)

### 3.3 Update `datetime.utcnow()` calls (25+ locations)

- `datetime.utcnow()` is deprecated in Python 3.12
- **Fix**: Replace with `datetime.now(tz=datetime.timezone.utc)`
- Similarly: `datetime.utcfromtimestamp(ts)` -> `datetime.fromtimestamp(ts, tz=datetime.timezone.utc)`

### 3.4 Remove dead Django version checks

- `das/utils/db/backends/postgis/base.py:126` -- `if django.VERSION < (3, 0):` is dead code

### 3.5 Testing changes to be aware of

- `assertFormError(response, 'form', ...)` signature changed in 4.1 -- pass form object directly
- `assertFormsetError` -> `assertFormSetError` (camelCase, Django 4.2)
- `assertQuerysetEqual` -> `assertQuerySetEqual` (camelCase, Django 4.2)

### 3.6 Admin changes to be aware of

- Admin logout now uses POST instead of GET (Django 4.1)
- `RadioSelect`/`CheckboxSelectMultiple` render in `<div>` instead of `<ul>` (Django 4.0)
- jQuery upgraded to 3.6.0 (Django 4.0)

---

## Recommended Upgrade Strategy

1. **Create a feature branch** for the upgrade
2. **Phase 1 first**: Fix all critical breaking changes before even attempting to run
3. **Set `USE_DEPRECATED_PYTZ = True`** as a transitional measure to defer the pytz->zoneinfo migration
4. **Upgrade third-party packages** one at a time, verifying compatibility
5. **Run the full test suite** after Phase 1 changes
6. **Phase 2**: Address deprecation warnings and behavioral changes
7. **Phase 3**: Cleanup at leisure
8. **Consider an intermediate stop at Django 4.0** if the jump is too large -- fix 4.0 breakage first, then upgrade to 4.2

## Database Requirements

- PostgreSQL 12+ required (Django 4.2 drops PG 11)
- Minimum `psycopg2` version: 2.8.4

## Python Requirements

- Python 3.8+ required (Django 4.0 drops 3.6/3.7)
