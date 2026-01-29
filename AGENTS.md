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

### Django Apps Structure
- `accounts/` - User management, permissions, and authentication
- `activity/` - Events, patrols, and alerting system
- `observations/` - Animal tracking, GPS data, and subject management
- `mapping/` - GIS integration, spatial data, and map services
- `sensors/` - IoT device handlers and data ingestion
- `analyzers/` - Real-time analysis (geofencing, proximity, immobility detection)
- `tracking/` - Source plugins for various GPS/telemetry providers
- `reports/` - Report generation and data distribution
- `utils/` - Shared utilities and common functionality


## Key Technologies
- Django 3.2
- Django REST Framework (for API development)
- python 3.10
- pytest for unittesting
- Celery (for background tasks)
- Redis (for caching and task queues)
- PostgreSQL 16
- Docker and Kubernetes for deployment

## Multi-Tenant Architecture

This system is multi-tenant aware. Most models have a `das_tenant` field that isolates data between tenants.

Key considerations:
- Data isolation at the database level
- Tenant context in requests and background tasks
- Tenant-specific configurations and permissions
- Cross-tenant queries require special authorization

## Configuration

### Settings Structure
- `das_server/settings.py` - Base settings
- `das_server/local_settings_docker.py` - Local development and prod overrides
- Environment variables configured via `.env` file for local overrides

### Key Environment Variables
- `DJANGO_SETTINGS_MODULE` - Points to settings module
- Database configuration via django-environ
- `DEBUG` and `DEV` flags for development mode

## Key File Locations

- Main Django project: `das/`
- Settings: `das/das_server/settings.py`
- Entry point: `das/manage.py`
- Dependencies: `pyproject.toml`
- Test configuration: `pytest.ini`
- Documentation: 'docs/'

## Django/Python Conventions
- Use Django’s class-based views (CBVs) with viewsets.
- Define API qparam filtering using drf basefilterbackend and django-filter library
- Leverage Django’s ORM for database interactions; avoid raw SQL queries unless necessary for performance.
- Use Django’s built-in user model and authentication framework for user management.
- Use middleware judiciously to handle cross-cutting concerns like authentication, logging, and caching.
- Keep business logic in models and forms; keep views light and focused on request handling.
- Use Django's URL dispatcher (urls.py) to define clear and RESTful URL patterns.
- Apply Django's security best practices (e.g., CSRF protection, SQL injection protection, XSS prevention).
- we prefer pytest. Fixtures can be found in conftest.py and run pytest from the project root to use the pytest.ini
- always use logging and not print
- Use test driven design principles. When fixing bugs, write the assertion unittest that exposes the bug, then fix the code to pass the test.
- pre-commit handles application of Pep rules including import sorting and pruning, so don't waste time on managing whitespace and other code formatting.
- Use python typing Protocol and not ABC for defining abstract classes. Rely on type checker to enforce all required methods are implemented.
- Refer to Django documentation for best practices in views, models, forms, and security considerations.
- Write API documentation in markdown, do this for new or updated APIs, documentation is stored in /docs


## Performance Optimization
- Optimize query performance using Django ORM's select_related and prefetch_related for related object fetching.
- Use Django’s cache framework with backend support (e.g., Redis or Memcached) to reduce database load.
- Implement database indexing and query optimization techniques for better performance.
- Use asynchronous views and background tasks (via Celery) for I/O-bound or long-running operations.
- Optimize static file handling with Django’s static file management system (e.g., WhiteNoise or CDN integration).

## Specialized Agents

For implementation work, use the specialized agents in `.claude/agents/`:
- `backend-developer` - Django development, database operations, testing
- `frontend-developer` - React development, Playwright E2E tests
- `code-reviewer` - Code review for quality, security, performance, multi-tenancy
