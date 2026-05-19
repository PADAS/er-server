"""Tests for analyzers migration 0064 — injecting analyzer_name into existing
analyzer-event schemas."""

from __future__ import annotations

import importlib
import json

import pytest

from activity.models import EventType
from core.models import DASTenant
from factories import EventCategoryFactory, EventTypeFactory

migration = importlib.import_module("analyzers.migrations.0064_add_analyzer_name_to_analyzer_eventtype_schemas")


class TestAddAnalyzerNameToSchema:
    def test_v1_definition_inside_schema_prepends_analyzer_name(self) -> None:
        schema = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "EventType Immobility",
                "type": "object",
                "properties": {
                    "name": {"type": "string", "title": "Name of animal"},
                    "details": {"type": "string", "title": "Details"},
                },
                "definition": ["name", "details"],
            }
        }

        changed = migration.add_analyzer_name_to_schema(schema, "1")

        assert changed is True
        assert list(schema["schema"]["properties"].keys()) == ["analyzer_name", "name", "details"]
        assert schema["schema"]["properties"]["analyzer_name"] == {
            "type": "string",
            "title": "Analyzer Name",
        }
        assert schema["schema"]["definition"] == ["analyzer_name", "name", "details"]

    def test_v1_definition_at_top_level_prepends_analyzer_name(self) -> None:
        schema = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "type": "object",
                "properties": {
                    "name": {"type": "string", "title": "Subject Name"},
                    "mean_value": {"type": "number", "title": "Mean Value"},
                },
            },
            "definition": ["name", "mean_value"],
        }

        changed = migration.add_analyzer_name_to_schema(schema, "1")

        assert changed is True
        assert list(schema["schema"]["properties"].keys()) == ["analyzer_name", "name", "mean_value"]
        assert schema["definition"] == ["analyzer_name", "name", "mean_value"]

    def test_v1_fieldset_definition_injects_into_first_items(self) -> None:
        schema = {
            "schema": {
                "type": "object",
                "properties": {
                    "subject_1_name": {"type": "string", "title": "Subject 1 Name"},
                },
            },
            "definition": [
                {
                    "type": "fieldset",
                    "title": "Analyzer Details",
                    "htmlClass": "col-lg-12",
                    "items": [],
                },
                {
                    "type": "fieldset",
                    "htmlClass": "col-lg-6",
                    "items": ["subject_1_name"],
                },
            ],
        }

        changed = migration.add_analyzer_name_to_schema(schema, "1")

        assert changed is True
        assert schema["definition"][0]["items"] == ["analyzer_name"]
        # Untouched second fieldset.
        assert schema["definition"][1]["items"] == ["subject_1_name"]
        assert "analyzer_name" in schema["schema"]["properties"]

    def test_v2_injects_into_json_ui_and_first_section(self) -> None:
        schema = {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "properties": {
                    "subject_name": {
                        "deprecated": False,
                        "title": "Subject Name",
                        "default": "",
                        "description": "",
                        "type": "string",
                    },
                },
                "required": [],
                "type": "object",
                "unevaluatedProperties": False,
            },
            "ui": {
                "fields": {
                    "subject_name": {
                        "conditionalDependents": [],
                        "parent": "section-2",
                        "type": "TEXT",
                        "inputType": "SHORT_TEXT",
                        "placeholder": "",
                    },
                },
                "sections": {
                    "section-2": {
                        "columns": 1,
                        "conditions": [],
                        "isActive": True,
                        "label": "",
                        "leftColumn": [{"name": "subject_name", "type": "field"}],
                        "rightColumn": [],
                    },
                },
                "order": ["section-2"],
            },
        }

        changed = migration.add_analyzer_name_to_schema(schema, "2")

        assert changed is True
        assert list(schema["json"]["properties"].keys()) == ["analyzer_name", "subject_name"]
        assert schema["ui"]["fields"]["analyzer_name"]["type"] == "TEXT"
        assert schema["ui"]["fields"]["analyzer_name"]["parent"] == "section-2"
        assert schema["ui"]["sections"]["section-2"]["leftColumn"] == [
            {"name": "analyzer_name", "type": "field"},
            {"name": "subject_name", "type": "field"},
        ]

    def test_v2_post_v1_to_v2_migration_uses_section_one(self) -> None:
        """If an admin already migrated the analyzer event type V1→V2, the
        produced V2 schema uses section-1 (not section-2). The migration must
        target that section and set the ui field's parent to match."""

        schema = {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "properties": {
                    "name": {
                        "deprecated": False,
                        "title": "Name of subject",
                        "type": "string",
                    },
                },
                "required": [],
                "type": "object",
                "unevaluatedProperties": False,
            },
            "ui": {
                "fields": {
                    "name": {
                        "conditionalDependents": [],
                        "parent": "section-1",
                        "type": "TEXT",
                        "inputType": "SHORT_TEXT",
                        "placeholder": "",
                    },
                },
                "sections": {
                    "section-1": {
                        "columns": 1,
                        "conditions": [],
                        "isActive": True,
                        "label": "",
                        "leftColumn": [{"name": "name", "type": "field"}],
                        "rightColumn": [],
                    },
                },
                "order": ["section-1"],
            },
        }

        changed = migration.add_analyzer_name_to_schema(schema, "2")

        assert changed is True
        assert "analyzer_name" in schema["json"]["properties"]
        assert schema["ui"]["fields"]["analyzer_name"]["parent"] == "section-1"
        assert schema["ui"]["sections"]["section-1"]["leftColumn"] == [
            {"name": "analyzer_name", "type": "field"},
            {"name": "name", "type": "field"},
        ]
        # section-2 must not be invented.
        assert "section-2" not in schema["ui"]["sections"]

    def test_v2_post_migration_with_multiple_sections_uses_order(self) -> None:
        """When a V1→V2 migration produces several sections, the first one in
        the declared order is the one that gets analyzer_name."""

        schema = {
            "json": {
                "properties": {
                    "name": {"title": "Name", "type": "string"},
                    "details": {"title": "Details", "type": "string"},
                },
                "type": "object",
            },
            "ui": {
                "fields": {
                    "name": {"parent": "section-1", "type": "TEXT", "inputType": "SHORT_TEXT"},
                    "details": {"parent": "section-3", "type": "TEXT", "inputType": "SHORT_TEXT"},
                },
                "sections": {
                    "section-3": {"leftColumn": [{"name": "details", "type": "field"}]},
                    "section-1": {"leftColumn": [{"name": "name", "type": "field"}]},
                },
                "order": ["section-1", "section-3"],
            },
        }

        changed = migration.add_analyzer_name_to_schema(schema, "2")

        assert changed is True
        assert schema["ui"]["fields"]["analyzer_name"]["parent"] == "section-1"
        assert schema["ui"]["sections"]["section-1"]["leftColumn"][0] == {
            "name": "analyzer_name",
            "type": "field",
        }
        # The unrelated section is untouched.
        assert schema["ui"]["sections"]["section-3"]["leftColumn"] == [
            {"name": "details", "type": "field"},
        ]

    def test_idempotent_when_analyzer_name_already_present(self) -> None:
        schema = {
            "schema": {
                "type": "object",
                "properties": {
                    "analyzer_name": {"type": "string", "title": "Analyzer Name"},
                    "name": {"type": "string", "title": "Subject Name"},
                },
                "definition": ["analyzer_name", "name"],
            }
        }
        original = json.loads(json.dumps(schema))

        changed = migration.add_analyzer_name_to_schema(schema, "1")

        assert changed is False
        assert schema == original

    def test_returns_false_when_no_properties(self) -> None:
        schema = {"schema": {"type": "object"}}
        original = json.loads(json.dumps(schema))

        changed = migration.add_analyzer_name_to_schema(schema, "1")

        assert changed is False
        assert schema == original

    def test_v2_real_world_geofence_break_post_v1_to_v2_migration(self) -> None:
        """Real-world example: a tenant who already ran the V1→V2 migration
        tool on geofence_break ends up with a single section-1 and no
        analyzer_name. Verify our migration injects it correctly."""

        schema = {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "additionalProperties": False,
                "properties": {
                    "name": {
                        "title": "Name of subject",
                        "type": "string",
                        "description": "",
                        "deprecated": False,
                    },
                    "total_fix_count": {
                        "title": "Total Fix Count",
                        "type": "number",
                        "description": "",
                        "deprecated": False,
                    },
                    "subject_heading": {
                        "title": "Subject Heading",
                        "type": "number",
                        "description": "",
                        "deprecated": False,
                    },
                    "contain_regions": {
                        "title": "Current Region",
                        "type": "string",
                        "description": "",
                        "deprecated": False,
                    },
                    "details": {
                        "title": "Details",
                        "type": "string",
                        "description": "",
                        "deprecated": False,
                    },
                    "subject_speed_kmhr": {
                        "title": "Subject Speed",
                        "type": "number",
                        "description": "",
                        "deprecated": False,
                    },
                    "geofence_name": {
                        "title": "Geofence Name",
                        "type": "string",
                        "description": "",
                        "deprecated": False,
                    },
                    "feature_group_name": {
                        "title": "Geofence Feature Group",
                        "type": "string",
                        "description": "",
                        "deprecated": False,
                    },
                },
                "required": [],
                "type": "object",
            },
            "ui": {
                "fields": {
                    "name": {
                        "inputType": "SHORT_TEXT",
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "TEXT",
                    },
                    "total_fix_count": {
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "NUMERIC",
                    },
                    "subject_heading": {
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "NUMERIC",
                    },
                    "contain_regions": {
                        "inputType": "SHORT_TEXT",
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "TEXT",
                    },
                    "details": {
                        "inputType": "SHORT_TEXT",
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "TEXT",
                    },
                    "subject_speed_kmhr": {
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "NUMERIC",
                    },
                    "geofence_name": {
                        "inputType": "SHORT_TEXT",
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "TEXT",
                    },
                    "feature_group_name": {
                        "inputType": "SHORT_TEXT",
                        "parent": "section-1",
                        "placeholder": "",
                        "type": "TEXT",
                    },
                },
                "headers": {},
                "order": ["section-1"],
                "sections": {
                    "section-1": {
                        "columns": 1,
                        "isActive": True,
                        "label": "",
                        "leftColumn": [
                            {"type": "field", "name": "name"},
                            {"type": "field", "name": "total_fix_count"},
                            {"type": "field", "name": "subject_heading"},
                            {"type": "field", "name": "contain_regions"},
                            {"type": "field", "name": "details"},
                            {"type": "field", "name": "subject_speed_kmhr"},
                            {"type": "field", "name": "geofence_name"},
                            {"type": "field", "name": "feature_group_name"},
                        ],
                        "rightColumn": [],
                    },
                },
            },
            "readonly": True,
        }

        changed = migration.add_analyzer_name_to_schema(schema, "2")

        assert changed is True

        # analyzer_name appears in the json properties and is first.
        assert list(schema["json"]["properties"].keys())[0] == "analyzer_name"
        assert schema["json"]["properties"]["analyzer_name"]["type"] == "string"

        # The original eight properties are still there with their values intact.
        assert schema["json"]["properties"]["geofence_name"]["title"] == "Geofence Name"
        assert schema["json"]["additionalProperties"] is False
        assert schema["readonly"] is True

        # UI field config points at the only section that exists.
        assert schema["ui"]["fields"]["analyzer_name"]["parent"] == "section-1"
        assert schema["ui"]["fields"]["analyzer_name"]["type"] == "TEXT"

        # analyzer_name is prepended to section-1's leftColumn; the rest is preserved.
        section = schema["ui"]["sections"]["section-1"]
        assert section["leftColumn"][0] == {"type": "field", "name": "analyzer_name"}
        assert [item["name"] for item in section["leftColumn"][1:]] == [
            "name",
            "total_fix_count",
            "subject_heading",
            "contain_regions",
            "details",
            "subject_speed_kmhr",
            "geofence_name",
            "feature_group_name",
        ]
        # section-2 is not invented.
        assert "section-2" not in schema["ui"]["sections"]

    def test_v2_with_existing_analyzer_name_is_noop(self) -> None:
        """A V2 schema that already has analyzer_name (e.g. it was V1→V2
        migrated *after* PR #3870 added the property) must be left alone."""

        schema = {
            "json": {
                "properties": {
                    "analyzer_name": {"title": "Analyzer Name", "type": "string"},
                    "name": {"title": "Name", "type": "string"},
                },
                "type": "object",
            },
            "ui": {
                "fields": {
                    "analyzer_name": {"parent": "section-1", "type": "TEXT"},
                    "name": {"parent": "section-1", "type": "TEXT"},
                },
                "sections": {
                    "section-1": {
                        "leftColumn": [
                            {"name": "analyzer_name", "type": "field"},
                            {"name": "name", "type": "field"},
                        ]
                    }
                },
            },
        }
        original = json.loads(json.dumps(schema))

        changed = migration.add_analyzer_name_to_schema(schema, "2")

        assert changed is False
        assert schema == original


@pytest.fixture
def analyzer_category():
    return EventCategoryFactory(value="analyzer_event", display="Analyzer Events")


@pytest.fixture
def immobility_eventtype(analyzer_category):
    schema = {
        "schema": {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "EventType Immobility",
            "type": "object",
            "properties": {
                "name": {"type": "string", "title": "Name of animal"},
                "details": {"type": "string", "title": "Details"},
            },
            "definition": ["name", "details"],
        }
    }
    return EventTypeFactory(
        value="immobility",
        display="Immobility",
        category=analyzer_category,
        schema=json.dumps(schema),
    )


@pytest.fixture
def non_analyzer_eventtype(analyzer_category):
    schema = {
        "schema": {
            "type": "object",
            "properties": {
                "details": {"type": "string", "title": "Details"},
            },
            "definition": ["details"],
        }
    }
    return EventTypeFactory(
        value="some_custom_event",
        display="Custom",
        category=analyzer_category,
        schema=json.dumps(schema),
    )


class FakeSchemaEditor:
    def __init__(self):
        self.connection = type("conn", (), {"alias": "default"})()


class FakeApps:
    _models = {
        ("activity", "EventType"): EventType,
        ("core", "DASTenant"): DASTenant,
    }

    def get_model(self, app_label: str, model_name: str):
        return self._models[(app_label, model_name)]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestForwardMigration:
    def test_updates_known_analyzer_event_types(self, immobility_eventtype) -> None:
        migration.forward(FakeApps(), FakeSchemaEditor())

        immobility_eventtype.refresh_from_db()
        parsed = json.loads(immobility_eventtype.schema)
        assert "analyzer_name" in parsed["schema"]["properties"]
        assert parsed["schema"]["definition"][0] == "analyzer_name"

    def test_skips_event_types_not_in_allowlist(self, non_analyzer_eventtype) -> None:
        original_schema = non_analyzer_eventtype.schema

        migration.forward(FakeApps(), FakeSchemaEditor())

        non_analyzer_eventtype.refresh_from_db()
        assert non_analyzer_eventtype.schema == original_schema

    def test_is_idempotent_when_run_twice(self, immobility_eventtype) -> None:
        migration.forward(FakeApps(), FakeSchemaEditor())
        immobility_eventtype.refresh_from_db()
        first_pass = immobility_eventtype.schema

        migration.forward(FakeApps(), FakeSchemaEditor())
        immobility_eventtype.refresh_from_db()
        assert immobility_eventtype.schema == first_pass

    def test_handles_invalid_json_gracefully(self, analyzer_category) -> None:
        # EventTypeFactory uses django_get_or_create=("value",), and
        # immobility_all_clear is created by activity/migrations/0050, so
        # passing schema= to the factory is silently ignored when the row
        # already exists. Force the invalid schema explicitly.
        bad = EventTypeFactory(
            value="immobility_all_clear",
            display="Immobility All Clear",
            category=analyzer_category,
        )
        EventType.objects.filter(pk=bad.pk).update(schema="not valid json{")

        migration.forward(FakeApps(), FakeSchemaEditor())
        bad.refresh_from_db()
        assert bad.schema == "not valid json{"

    def test_templated_v1_schema_is_patched_and_templates_preserved(self, analyzer_category) -> None:
        """A V1 schema with `{{enum___...}}` Django template tokens (e.g. an
        admin-customised geofence_break with a choice field) is not valid JSON.
        preprocess_template_vars makes it parseable; after injection the saved
        schema must still contain the bare {{...}} tokens so the runtime
        renderer can expand them."""

        templated_schema = (
            "{\n"
            '  "schema": {\n'
            '    "$schema": "http://json-schema.org/draft-04/schema#",\n'
            '    "type": "object",\n'
            '    "properties": {\n'
            '      "name": {"type": "string", "title": "Name of subject"},\n'
            '      "region": {\n'
            '        "type": "string",\n'
            '        "title": "Region",\n'
            '        "enum": {{enum___region___values}},\n'
            '        "enumNames": {{enum___region___names}}\n'
            "      }\n"
            "    },\n"
            '    "definition": ["name", "region"]\n'
            "  }\n"
            "}"
        )
        et = EventTypeFactory(
            value="geofence_break",
            display="Geofence Break",
            category=analyzer_category,
            schema=templated_schema,
        )

        migration.forward(FakeApps(), FakeSchemaEditor())
        et.refresh_from_db()

        # Templates survive the round trip — both placeholders are present and
        # unquoted, exactly as the schema renderer expects.
        assert "{{enum___region___values}}" in et.schema
        assert "{{enum___region___names}}" in et.schema
        assert '"{{enum___region___values}}"' not in et.schema
        assert '"{{enum___region___names}}"' not in et.schema

        # Once we expand the templates with empty values, the result is parseable
        # JSON containing analyzer_name as the first definition entry.
        renderable = et.schema.replace("{{enum___region___values}}", "[]").replace("{{enum___region___names}}", "[]")
        parsed = json.loads(renderable)
        assert "analyzer_name" in parsed["schema"]["properties"]
        assert parsed["schema"]["definition"][0] == "analyzer_name"

    def test_uses_v2_path_when_eventtype_version_is_2(self, analyzer_category) -> None:
        """An EventType whose model row reports version="2" — e.g. because a
        tenant has already migrated it via the V1→V2 tool — must take the V2
        injection path, regardless of what the stored schema looks like."""

        v2_schema = {
            "json": {
                "properties": {"name": {"title": "Name", "type": "string"}},
                "type": "object",
            },
            "ui": {
                "fields": {"name": {"parent": "section-1", "type": "TEXT"}},
                "sections": {
                    "section-1": {"leftColumn": [{"name": "name", "type": "field"}]},
                },
                "order": ["section-1"],
            },
        }
        et = EventTypeFactory(
            value="geofence_break",
            display="Geofence Break",
            category=analyzer_category,
            schema=json.dumps(v2_schema),
            version=EventType.VersionChoices.VERSION_2,
        )

        migration.forward(FakeApps(), FakeSchemaEditor())
        et.refresh_from_db()
        parsed = json.loads(et.schema)
        assert "analyzer_name" in parsed["json"]["properties"]
        assert parsed["ui"]["fields"]["analyzer_name"]["parent"] == "section-1"
        assert parsed["ui"]["sections"]["section-1"]["leftColumn"][0] == {
            "name": "analyzer_name",
            "type": "field",
        }
