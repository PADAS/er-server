import json
from pathlib import Path

import pytest

from rest_framework.test import APIRequestFactory

from activity.models import EventType
from activity.schemas.migration.choice_processor import ChoiceProcessor
from activity.schemas.migration.logger import LogContext, MigrationLogger
from activity.schemas.migration.service import MigrationResult, MigrationService
from choices.models import Choice
from factories import EventTypeFactory

# =============================================================================
# ChoiceProcessor Fixtures
# =============================================================================


CHOICES_BASE_URL = "/api/v2.0/schemas/choices.json"


@pytest.fixture
def choices_base_url():
    """The absolute base URL used for $ref rewriting in tests."""
    return CHOICES_BASE_URL


def _load_existing_choices():
    """Load existing choice fields from the DB (mirrors MigrationService.load_existing_choice_fields)."""
    fields = {}
    for field_name, value in Choice.objects.filter(model=Choice.EVENT_MODEL, is_active=True).values_list(
        "field", "value"
    ):
        fields.setdefault(field_name, []).append(value)
    return fields


@pytest.fixture
def choice_processor(choices_base_url):
    """Eager ChoiceProcessor instance (no DB choices loaded)."""
    return ChoiceProcessor()


@pytest.fixture
def make_choice_processor(choices_base_url):
    """Factory fixture that loads existing choices from DB at call time.

    Use this instead of choice_processor when the test creates DB Choice
    objects before building the processor.
    """

    def _create(event_type_value="", existing_choices=None):
        processor = ChoiceProcessor()
        processor.event_type_value = event_type_value
        processor.existing_choices = existing_choices or _load_existing_choices()
        return processor

    return _create


@pytest.fixture
def choice_processor_with_event_type(choices_base_url):
    """Factory fixture for ChoiceProcessor with event_type_value (loads DB choices)."""

    def _create(event_type_value="test_event", existing_choices=None):
        processor = ChoiceProcessor()
        processor.event_type_value = event_type_value
        processor.existing_choices = existing_choices or _load_existing_choices()
        return processor

    return _create


# =============================================================================
# Choice Model Fixtures
# =============================================================================


@pytest.fixture
def create_choice():
    """Factory fixture for creating Choice objects."""

    def _create(field, value, display=None, ordernum=0):
        return Choice.objects.create(
            model=Choice.EVENT_MODEL,
            field=field,
            value=value,
            display=display or value.title(),
            ordernum=ordernum,
        )

    return _create


@pytest.fixture
def create_choice_field(create_choice):
    """Factory fixture for creating a complete choice field with multiple values."""

    def _create(field_name, values):
        """
        Args:
            field_name: Name of the choice field
            values: List of (value, display) tuples or just value strings
        """
        choices = []
        for i, v in enumerate(values):
            if isinstance(v, tuple):
                value, display = v
            else:
                value, display = v, v.title()
            choices.append(create_choice(field_name, value, display, i))
        return choices

    return _create


# =============================================================================
# Hardcoded Values Fixtures
# =============================================================================


@pytest.fixture
def hardcoded_values():
    """Factory for creating hardcoded value lists (output format of extract_hardcoded_choices)."""

    def _create(*items):
        """
        Args:
            items: Tuples of (value, display) or just value strings
        Returns:
            List of {"value": ..., "display": ...} dicts
        """
        result = []
        for item in items:
            if isinstance(item, tuple):
                value, display = item
            else:
                value, display = item, item.title()
            result.append({"value": value, "display": display})
        return result

    return _create


# =============================================================================
# V2 Schema Builder Fixtures
# =============================================================================


@pytest.fixture
def hardcoded_field_schema():
    """Factory for creating V2 hardcoded choice field schemas."""

    def _create(*items):
        """
        Args:
            items: Tuples of (const, title) or just const strings
        Returns:
            V2 field schema with anyOf/oneOf structure
        """
        one_of = []
        for item in items:
            if isinstance(item, tuple):
                const, title = item
            else:
                const, title = item, item.title()
            one_of.append({"const": const, "title": title})

        return {"anyOf": [{"title": "Hardcoded", "type": "string", "oneOf": one_of}]}

    return _create


@pytest.fixture
def v2_schema_with_fields(hardcoded_field_schema):
    """Factory for creating complete V2 schemas with multiple fields."""

    def _create(fields_config):
        """
        Args:
            fields_config: Dict of {field_name: list of values} or {field_name: {"type": "string"}}
        Returns:
            Complete V2 schema structure
        """
        properties = {}
        for field_name, config in fields_config.items():
            if isinstance(config, dict) and "type" in config:
                properties[field_name] = config
            else:
                properties[field_name] = hardcoded_field_schema(*config)

        return {"json": {"properties": properties}}

    return _create


# =============================================================================
# JSON Schema Fixtures
# =============================================================================


@pytest.fixture
def json_schema_fixture(request):
    """Load a JSON schema fixture file by name."""
    fixture_name = request.param
    fixture_path = Path(__file__).parent.parent / "fixtures" / f"{fixture_name}.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def auto_generate_v1_marker_schema():
    """V1 auto-generate marker schema for testing (as used in Django admin)."""
    return {
        "auto-generate": True,
        "description": "This schema is a placeholder, to be replaced automatically when new data is recorded.",
        "schema": {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Placeholder schema",
            "type": "object",
            "readonly": True,
            "properties": {
                "placeholder": {
                    "type": "string",
                    "title": "Placeholder",
                    "default": "This schema will be auto-generated when event data is recorded.",
                }
            },
        },
        "definition": ["placeholder"],
    }


@pytest.fixture
def auto_generate_v2_marker_schema():
    """V2 auto-generate marker schema for testing."""
    return {
        "auto-generate": True,
        "description": "This schema is a placeholder, to be replaced automatically when new data is recorded.",
        "json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "properties": {
                "placeholder": {
                    "default": "This schema will be auto-generated when event data is recorded.",
                    "deprecated": False,
                    "title": "Placeholder",
                    "type": "string",
                }
            },
            "required": [],
            "type": "object",
            "unevaluatedProperties": False,
        },
        "ui": {
            "fields": {
                "placeholder": {
                    "conditionalDependents": [],
                    "inputType": "SHORT_TEXT",
                    "parent": "section-1",
                    "placeholder": "",
                    "type": "TEXT",
                }
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "conditions": [],
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": "placeholder", "type": "field"}],
                    "rightColumn": [],
                }
            },
        },
    }


# =============================================================================
# MigrationService Fixtures
# =============================================================================


@pytest.fixture
def mock_request(admin_user):
    """Create a mock DRF request with an admin user."""
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = admin_user
    request.method = "GET"
    return request


@pytest.fixture
def migration_logger():
    """MigrationLogger with a test LogContext (no real tenant resolution)."""
    context = LogContext(
        migration_request_id="MR-test-00000000",
        tenant_name="test-tenant",
        dry_run=True,
    )
    return MigrationLogger(context=context)


@pytest.fixture
def migration_service(mock_request, migration_logger):
    """Basic MigrationService with dry_run=True (default)."""
    return MigrationService(request=mock_request, logger=migration_logger)


@pytest.fixture
def make_migration_service(mock_request):
    """Factory fixture that loads existing choices from DB at call time.

    Use this instead of migration_service when the test creates DB Choice
    objects before calling process_choices() directly.
    """

    def _create(dry_run=True):
        context = LogContext(
            migration_request_id="MR-test-00000000",
            tenant_name="test-tenant",
            dry_run=dry_run,
        )
        ml = MigrationLogger(context=context)
        service = MigrationService(request=mock_request, dry_run=dry_run, logger=ml)
        service.existing_choices = service.load_existing_choice_fields()
        return service

    return _create


@pytest.fixture
def migration_service_live(mock_request):
    """MigrationService with dry_run=False for testing persistence."""
    context = LogContext(
        migration_request_id="MR-test-00000000",
        tenant_name="test-tenant",
        dry_run=False,
    )
    ml = MigrationLogger(context=context)
    return MigrationService(request=mock_request, dry_run=False, logger=ml)


@pytest.fixture
def v1_event_type(cat1_cat2_categories):
    """Create a V1 EventType for testing migration."""
    category, _ = cat1_cat2_categories
    v1_schema = json.dumps(
        {
            "properties": {
                "status": {
                    "type": "string",
                    "title": "Status",
                    "enum": ["open", "closed", "pending"],
                    "enumNames": ["Open", "Closed", "Pending"],
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                },
            },
            "definition": ["status", "description"],
        }
    )
    return EventTypeFactory.create(
        value="test_event_type_v1",
        display="Test Event Type V1",
        category=category,
        schema=v1_schema,
        version=EventType.VersionChoices.VERSION_1,
    )


@pytest.fixture
def v2_event_type(cat1_cat2_categories):
    """Create a V2 EventType (should be skipped by migration)."""
    category, _ = cat1_cat2_categories
    v2_schema = json.dumps(
        {
            "json": {"properties": {}},
            "ui": {},
        }
    )
    return EventTypeFactory.create(
        value="v2_event_type",
        display="V2 Event Type",
        category=category,
        schema=v2_schema,
        version=EventType.VersionChoices.VERSION_2,
    )


@pytest.fixture
def create_v1_event_type(cat1_cat2_categories):
    """Factory fixture for creating V1 EventTypes with custom schemas."""

    def _create(value, schema=None, display=None):
        category, _ = cat1_cat2_categories
        if schema is None:
            schema = json.dumps({"properties": {}, "definition": []})
        elif isinstance(schema, dict):
            schema = json.dumps(schema)
        return EventTypeFactory.create(
            value=value,
            display=display or value.replace("_", " ").title(),
            category=category,
            schema=schema,
            version=EventType.VersionChoices.VERSION_1,
        )

    return _create


# =============================================================================
# MigrationResult Fixtures
# =============================================================================


@pytest.fixture
def migration_result(migration_logger):
    """Factory fixture for creating MigrationResult objects."""

    def _create(event_type_value="test_event", **kwargs):
        return MigrationResult(
            event_type_value=event_type_value,
            log=migration_logger.for_event_type(event_type_value),
            **kwargs,
        )

    return _create
