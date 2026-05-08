# Python 3.10 → 3.12 Upgrade Plan

## Context

The project hard-pins Python 3.10 (`requires-python = ">=3.10,<3.11"` in `pyproject.toml`). Python 3.10 reaches end-of-life in October 2026. Python 3.12 offers faster interpreter performance (~5–15%), improved error messages, `@override` typing support, and security backports through 2028.

The base Docker image (`osgeo/gdal:ubuntu-small-3.12.3`) runs Ubuntu 24.04, which ships Python 3.12 as the system default — so no base image change is required.

The migration is **medium complexity**. No breaking Python syntax changes are needed in application code. The primary work is:

1. Updating version pins in six files
2. Bumping four third-party packages whose pinned versions have no Python 3.12 wheels
3. Regenerating `uv.lock`
4. Cleaning up one dead-code block

Estimated effort: **~8–11 hours** (3–5 engineering days including testing).

---

## Compatibility Audit

### Version Pins to Update

| File | Line(s) | Current | Target |
|------|---------|---------|--------|
| `pyproject.toml` | 9 | `requires-python = ">=3.10,<3.11"` | `">=3.12,<3.13"` |
| `pyproject.toml` | 142 | `"Programming Language :: Python :: 3.10"` | `"Programming Language :: Python :: 3.12"` |
| `pyproject.toml` | 149 | `target-version = ['py310']` (Black) | `['py312']` |
| `Dockerfile.mt` | 24 | `uv venv --python=python3.10` | `uv venv --python=python3.12` |
| `circleci-docker/Dockerfile` | 26 | `uv venv --python=python3.10` | `uv venv --python=python3.12` |
| `.devcontainer/Dockerfile` | 4, 7, 8 | `3.10` / `3.10.18` | `3.12` / latest 3.12 patch |

`uv.lock` line 3 (`requires-python = "==3.10.*"`) updates automatically when `uv lock` is re-run.

> Docs CI already uses Python 3.12 — no changes needed in `.github/workflows/` or `.circleci/config.yml` docs jobs.

### Packages Requiring Version Bumps

These four packages have no `cp312` wheels at their pinned version and must be upgraded in `pyproject.toml`:

| Package | Current Pin | Issue | Target |
|---------|------------|-------|--------|
| `celery` | `==5.3.0` | Python 3.12 compat fixed in 5.3.4 (removes internal `imp` usage) | `>=5.3.6,<6` |
| `markupsafe` | `==2.0.1` | No `cp312` wheel exists; 2.1.x added them | `>=2.1.5` |
| `lxml` | `==4.9.2` | `cp312` wheels added in 4.9.3+; 5.x has full support | `>=5.2.0` |
| `cython` | `==0.29.35` | 0.x series predates Python 3.12; 3.x added support | See note below |

**Cython note:** No `.pyx` files exist in `das/`. Cython is likely pulled in as a build-time transitive dep (e.g. by `rasterio`). Confirm with `uv tree --package cython`. If it is not a direct runtime dep, remove it from `[project].dependencies` entirely; if it is, upgrade to `>=3.0.10`.

**Downstream impact of `lxml` upgrade:**
- `python-docx==0.8.11` depends on lxml — upgrade to `>=1.1.0` alongside lxml
- `fastkml[lxml]` — verify no breaking lxml 5.x API changes

### Dead Code to Remove

**`das/reports/environment.py:681–688`** — `import imp` inside an `else:` block guarded by `if not PY2 or PYPY:`. This branch can never execute on Python 3 (`PY2` is always `False`). Remove the entire `else:` block. `imp` was removed in Python 3.12.

### Code Audit: No Action Required

| Check | Result |
|-------|--------|
| Removed stdlib modules (`distutils`, `cgi`, `asynchat`, `imghdr`, etc.) | None found |
| `pkg_resources` usage | None found |
| `setup.py` / `distutils` | None found (uses `pyproject.toml`) |
| `asyncio.coroutine` decorator (removed in 3.11) | None found |
| Deprecated `datetime.utcnow()` | None found |
| `six` imports | Found in 4 files — `six` itself is Python 3 compatible, **not a blocker** |
| `from __future__ import unicode_literals` (~87 files) | No-op in Python 3, **not a blocker** — clean up separately |
| `collections.abc` usage | Already correct |

---

## Migration Steps

### Step 1 — Audit Cython dependency

```bash
uv tree --package cython
```

Determine if `cython` is a direct runtime requirement or only a transitive build dep. This decision gates whether to remove or upgrade it in Step 3.

### Step 2 — Confirm base image ships Python 3.12

```bash
docker run --rm osgeo/gdal:ubuntu-small-3.12.3 python3 --version
```

Expected: `Python 3.12.x`. No base image change is needed if this passes.

### Step 3 — Update `pyproject.toml`

Apply all of the following changes:

1. `requires-python = ">=3.10,<3.11"` → `">=3.12,<3.13"`
2. Classifier `Python :: 3.10` → `Python :: 3.12`
3. Black `target-version = ['py310']` → `['py312']`
4. `"celery==5.3.0"` → `"celery>=5.3.6,<6"`
5. `"markupsafe==2.0.1"` → `"markupsafe>=2.1.5"`
6. `"lxml==4.9.2"` → `"lxml>=5.2.0"`
7. `"python-docx==0.8.11"` → `"python-docx>=1.1.0"`
8. `"cython==0.29.35"` → remove (if not a direct dep) or `"cython>=3.0.10"`

### Step 4 — Remove dead code in `environment.py`

In `das/reports/environment.py`, delete the `else:` block at lines 681–688 that contains `import imp`. The surrounding `if not PY2 or PYPY:` branch handles all Python 3 paths.

### Step 5 — Regenerate the lock file

```bash
uv lock --python=python3.12
```

Review `git diff uv.lock` to confirm all `cp310-cp310` wheels replaced with `cp312-cp312` equivalents. Flag any package that fell back to sdist-only when a wheel was expected.

### Step 6 — Run local smoke test

```bash
uv sync --group dev --python=python3.12
python -c "import django; import celery; import lxml; import rasterio; print('OK')"
python manage.py check
```

### Step 7 — Update Dockerfiles

- `Dockerfile.mt` line 24: `python3.10` → `python3.12`
- `circleci-docker/Dockerfile` line 26: `python3.10` → `python3.12`
- `.devcontainer/Dockerfile`:
  - Line 4 (comment): update to `# python 3.12.x`
  - Line 7: `ARG PYTHON_VERSION_ID="3.10"` → `"3.12"`
  - Line 8: `ARG PYTHON_VERSION="3.10.18"` → latest 3.12 patch (e.g. `"3.12.10"`)

### Step 8 — Run full test suite

```bash
pytest das/ -x --tb=short
```

Focus areas if failures occur:
- `das/reports/` — exercises lxml, python-docx, and the Jinja2 environment
- `das/activity/` — exercises Celery tasks and celery-once
- `das/mapping/` and `das/analyzers/` — exercise rasterio, pyproj, shapely, geopandas

### Step 9 — Rebuild CI Docker image

The CircleCI test executor uses `circleci-docker/Dockerfile`. After Step 7, rebuild and push that image so CI picks up Python 3.12. Tag the old `python3.10` image before pushing as a rollback point.

---

## Testing Strategy

1. `pytest das/` — 0 failures required
2. `mypy das/` — 0 new errors introduced
3. `python manage.py check` — no warnings
4. Celery worker and beat start cleanly
5. Report generation produces valid `.docx` output (smoke-test the reports app)
6. Full CircleCI pipeline passes on the PR

---

## Rollback Plan

All changes are confined to config files, `uv.lock`, and one dead-code deletion. There are no Django model changes or database migrations. Rollback = revert the PR. Before pushing the new CircleCI Docker image, tag the existing one so CI can be pointed back to it if needed.

---

## Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | `requires-python`, classifiers, Black target, 5 package version bumps |
| `uv.lock` | Regenerated by `uv lock` — do not edit manually |
| `Dockerfile.mt` | Line 24: `python3.10` → `python3.12` |
| `circleci-docker/Dockerfile` | Line 26: `python3.10` → `python3.12` |
| `.devcontainer/Dockerfile` | Lines 4, 7, 8: Python version ARGs |
| `das/reports/environment.py` | Remove dead `import imp` else-block (lines ~681–688) |
