# UV Guide for DAS

Quick reference for using UV (Python package manager) in the DAS project.

## Installation

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or homebrew (macOS)
brew install uv
```

## Project Setup

```bash
# Initial setup
uv venv
source .venv/bin/activate  # Linux/macOS
uv sync --group dev --find-links dependencies/wheelhouse

# Daily development
cd das
uv run python manage.py runserver 8080 --settings=das_server.local_settings_docker
uv run pytest
```

## Essential Commands

### Dependencies
```bash
# Install all dependencies
uv sync --group dev --find-links dependencies/wheelhouse

# Add new dependency
uv add package-name
uv add --group dev package-name  # dev dependency

# Update dependencies
uv lock --upgrade
uv sync --group dev
```

### Running Commands
```bash
# Django commands
uv run python manage.py migrate
uv run python manage.py collectstatic --no-input
uv run python manage.py test

# Server processes
uv run gunicorn das_server.wsgi
uv run pytest
```

### Package Inspection
```bash
uv tree --package django  # Show dependency tree
uv tree                   # Show full tree
```

## Key Files

- `pyproject.toml` - Main dependencies and project config
- `uv.lock` - Locked versions (commit this!)
- `dependencies/wheelhouse/` - Local wheel files

## Troubleshooting

```bash
# Recreate environment
rm -rf .venv
uv venv
uv sync --group dev --find-links dependencies/wheelhouse

# Regenerate lock file
rm uv.lock
uv lock

# Check specific package
uv tree --package problematic-package
```

## Migration from pip

| pip | UV |
|-----|-----|
| `pip install -r requirements.txt` | `uv sync` |
| `pip install -r requirements-dev.txt` | `uv sync --group dev` |
| `pip install package` | `uv add package` |
| `python manage.py` | `uv run python manage.py` |

## Best Practices

1. Always commit `uv.lock`
2. Use `uv sync --group dev` for development
3. Use `uv run` for all Python commands
4. Update with `uv lock --upgrade` regularly
