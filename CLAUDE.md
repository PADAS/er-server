# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Who am I
You are an expert python developer with expertise in Django, SpiceDB, Postgresql, GCP, multi-tenancy and highly scalable solutions.

## Project Overview

EarthRanger (DAS - Domain Awareness System) is a Django-based web application for wildlife conservation and domain awareness. This is a multi-tenant system that tracks wildlife, manages events, handles patrols, and provides real-time monitoring capabilities.

## Core Architecture

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

### Key Technologies
- Django 3.2 with PostgreSQL + PostGIS
- Celery for background tasks
- Redis for caching and pub/sub
- Real-time WebSocket communication
- Docker containerization

## Development Commands

### Running the Application
```bash
# Start storage containers (Redis and PostgreSQL)
make start

# Run Django development server
cd das
python manage.py runserver 8080
# OR with specific settings
python manage.py runserver 8080 --settings=das_server.local_settings_docker
```

### Testing
```bash
# Run all tests
cd das
python -m pytest

# Run specific test module
python -m pytest observations/tests/test_models.py

# Run with coverage
python -m pytest --cov

# Django test runner (alternative)
python manage.py test
```

### Database Operations
```bash
cd das
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Load initial data
python manage.py loaddata <fixture_file>
```

### Code Quality
The project uses Django's built-in code style. Common linting/formatting commands should be run before committing changes. We write pytest style unittests for views and other code.

## Performance Optimization
- Optimize query performance using Django ORM's select_related and prefetch_related for related object fetching.
- Use Django’s cache framework with backend support (e.g., Redis or Memcached) to reduce database load.
- Implement database indexing and query optimization techniques for better performance.
- Use asynchronous views and background tasks (via Celery) for I/O-bound or long-running operations.
- Optimize static file handling with Django’s static file management system (e.g., WhiteNoise or CDN integration).


## Multi-Tenant Architecture

This system is multi-tenant aware. Most models have a `das_tenant` field that isolates data between tenants. When working with models:
- Use tenant-aware managers (most models have custom managers)
- Be aware of tenant context in views and serializers
- Migrations often include tenant-specific data population

## Important Configuration

### Settings Structure
- `das_server/settings.py` - Base settings
- `das_server/local_settings_docker.py` - Local development and prod overrides
- Environment variables configured via `.env` file, for local overrides

### Key Environment Variables
- `DJANGO_SETTINGS_MODULE` - Points to settings module
- Database configuration via django-environ
- DEBUG and DEV flags for development mode

## Common Development Patterns

### Model Structure
- Most models inherit from timestamped mixins
- UUID primary keys are common
- Tenant-aware foreign keys (`TenantForeignKey`)
- Extensive use of JSONField for flexible data

### API Patterns
- Django REST Framework for APIs
- Permission-based access control
- Geographic/spatial query support based on GDAL
- Real-time updates via WebSockets using python-socketio library
- Use Django templates for rendering HTML and DRF serializers for JSON responses.
- Keep business logic in models and forms; keep views light and focused on request handling.
- Use Django's URL dispatcher (urls.py) to define clear and RESTful URL patterns.
- Apply Django's security best practices (e.g., CSRF protection, SQL injection protection, XSS prevention).
- Use Django’s built-in tools for testing (pytest and pytest-django) to ensure code quality and reliability.


### Background Processing
- Celery tasks for analysis, notifications, and data processing
- Periodic tasks via Celery Beat
- Pub/Sub messaging for real-time updates using Kombu

## Testing Considerations

- Tests are located in `tests/` directories within each app
- Uses Django's test framework with pytest
- Test data often uses factories (see `factories.py` files)
- Test data uses fixtures found in conftest.py
- Tenant-aware testing required for multi-tenant features
- Mock external services (GPS providers, mapping services)

## Key File Locations

- Main Django project: `das/`
- Settings: `das/das_server/settings.py`
- Entry point: `das/manage.py`
- Dependencies: `dependencies/requirements.txt`
- Test configuration: `pytest.ini`
