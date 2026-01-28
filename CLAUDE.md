# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

### Key Technologies
- Django 3.2 with PostgreSQL + PostGIS
- Celery for background tasks
- Redis for caching and pub/sub
- Real-time WebSocket communication
- Docker containerization

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

## Specialized Agents

For implementation work, use the specialized agents in `.claude/agents/`:
- `backend-developer` - Django development, database operations, testing
- `frontend-developer` - React development, Playwright E2E tests
- `code-reviewer` - Code review for quality, security, performance, multi-tenancy
