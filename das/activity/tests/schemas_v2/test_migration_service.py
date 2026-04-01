"""Tests for MigrationService - schema migration orchestration."""

import json
from unittest.mock import patch

import pytest

from activity.models import EventType
from activity.schemas.migration.choice_processor import (
    ChoiceProcessor,
    HardcodedChoiceResolution,
    ResolutionStrategy,
)
from activity.schemas.migration.logger import LogContext, MigrationLogger
from activity.schemas.migration.service import (
    MigrationRequest,
    MigrationResult,
    MigrationService,
    ResolvedHardcodedChoice,
)
from choices.models import Choice

_test_context = LogContext(migration_request_id="MR-test", tenant_name="test", dry_run=True)
_test_logger = MigrationLogger(context=_test_context)


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_success_when_no_errors(self):
        result = MigrationResult(event_type_value="test")
        assert result.success is True

    def test_failure_when_errors_present(self):
        result = MigrationResult(event_type_value="test", errors=["Something failed"])
        assert result.success is False


class TestMigrationRequest:
    """Tests for MigrationRequest input normalization."""

    def test_hardcoded_choice_resolution_from_dict(self):
        resolution = HardcodedChoiceResolution.from_dict(
            {
                "property_path": ["severity"],
                "strategy": "USE_EXISTING",
                "choice_field_name": "severity",
            }
        )

        assert resolution.property_path == ["severity"]
        assert resolution.strategy == ResolutionStrategy.USE_EXISTING
        assert resolution.choice_field_name == "severity"

    def test_from_input_accepts_string(self):
        request = MigrationRequest.from_input("fire_rep")

        assert request.event_type_value == "fire_rep"
        assert request.hardcoded_choices_resolutions is None

    def test_from_input_accepts_dict(self):
        request = MigrationRequest.from_input({"event_type_value": "fire_rep"})

        assert request.event_type_value == "fire_rep"
        assert request.hardcoded_choices_resolutions is None

    def test_from_input_normalizes_hardcoded_choice_resolution_dicts(self):
        request = MigrationRequest.from_input(
            {
                "event_type_value": "fire_rep",
                "hardcoded_choices_resolutions": [
                    {
                        "property_path": ["severity"],
                        "strategy": "USE_EXISTING",
                        "choice_field_name": "severity",
                    }
                ],
            }
        )

        assert request.hardcoded_choices_resolutions is not None
        resolution = request.hardcoded_choices_resolutions[0]
        assert isinstance(resolution, HardcodedChoiceResolution)
        assert resolution.property_path == ["severity"]
        assert resolution.strategy == ResolutionStrategy.USE_EXISTING
        assert resolution.choice_field_name == "severity"

    def test_from_input_returns_existing_instance(self):
        request = MigrationRequest(event_type_value="fire_rep")

        assert MigrationRequest.from_input(request) is request


class TestMigrationServiceInit:
    """Tests for MigrationService initialization."""

    def test_init_with_defaults(self, migration_service, mock_request):
        assert migration_service.request == mock_request
        assert migration_service.dry_run is True  # Default

    def test_init_with_dry_run_false(self, migration_service_live):
        assert migration_service_live.dry_run is False


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestMigrateSingle:
    """Tests for single-item migration via `migrate([...])[0]`."""

    def test_event_type_not_found(self, migration_service):
        result = migration_service.migrate(["nonexistent_type"])[0]

        assert result.success is False
        assert "not found" in result.errors[0]

    def test_skips_v2_event_type(self, migration_service, v2_event_type):
        result = migration_service.migrate([v2_event_type.value])[0]

        assert result.success is False
        assert "is not V1" in result.errors[0]

    def test_invalid_json_schema(self, migration_service, v1_event_type):
        """EventType with unparseable JSON schema should fail with a clear error."""
        v1_event_type.schema = "not valid json {{"
        v1_event_type.save(update_fields=["schema"])

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is False
        assert any("Invalid JSON in schema" in e for e in result.errors)
        assert result.v2_schema is None

    @patch("activity.schemas.migration.service.transform_schema")
    def test_dry_run_does_not_persist(self, mock_transform, migration_service, v1_event_type):
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is True
        # Reload from DB - should still be V1
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1

    @patch.object(MigrationService, "can_modify_event_type", return_value=False)
    @patch("activity.schemas.migration.service.transform_schema")
    def test_denies_when_no_permission(self, mock_transform, mock_perm, migration_service_live, v1_event_type):
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}

        result = migration_service_live.migrate([v1_event_type.value])[0]

        assert result.success is False
        assert "Permission denied" in result.errors[0]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestDryRunParity:
    """Regression tests: if a schema passes dry_run, it should also pass when persisting."""

    @patch.object(MigrationService, "can_modify_event_type", return_value=True)
    def test_duplicate_choice_values_persist_same_as_dry_run(
        self,
        mock_perm,
        make_migration_service,
        v1_event_type,
    ):
        """Duplicate enum values can exist in V1 schemas.

        Migration should deduplicate them during analysis so persistence doesn't
        violate the Choice unique constraint on (tenant, model, field, value).
        """
        v1_schema = {
            "definition": ["single_select"],
            "description": "This schema will be used for regression testing in the mobile app",
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "icon_id": "generic_rep",
                "id": "https://mobile-bash.pamdas.org/api/v1.0/activity/events/schema/eventtype/single_select_query_no_required",
                "image_url": "https://mobile-bash.pamdas.org/static/generic-black.svg",
                "properties": {
                    "single_select": {
                        "enum": ["new", "new"],
                        "enumNames": {"new": "New/Fresh", "old": "New/Fresh"},
                        "title": "I'm a single select query",
                        "type": "string",
                    }
                },
                "title": "String",
                "type": "object",
            },
        }

        v1_event_type.schema = json.dumps(v1_schema)
        v1_event_type.save()

        dry_run_service = make_migration_service(dry_run=True)
        dry_run_result = dry_run_service.migrate([v1_event_type.value])[0]
        assert dry_run_result.success is True
        assert len(dry_run_result.hardcoded_choices) == 1
        assert len(dry_run_result.resolved_hardcoded_choices) == 1
        assert dry_run_result.resolved_hardcoded_choices[0].resolution.strategy == ResolutionStrategy.CREATE_NEW

        live_service = make_migration_service(dry_run=False)
        live_results = live_service.migrate([v1_event_type.value])
        assert live_results[0].success is True

        # Only one DB row should exist for the duplicated value
        field_name = live_results[0].resolved_hardcoded_choices[0].resolution.choice_field_name
        assert Choice.objects.filter(model=Choice.EVENT_MODEL, field=field_name).count() == 1

    @patch("activity.schemas.migration.service.transform_schema")
    @patch.object(MigrationService, "can_modify_event_type", return_value=True)
    def test_persists_when_not_dry_run(self, mock_perm, mock_transform, migration_service_live, v1_event_type):
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}

        results = migration_service_live.migrate([v1_event_type.value])

        assert results[0].success is True
        # Reload from DB - should be V2 now
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_2


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestMigrate:
    """Tests for migrate method (batch migration)."""

    @patch("activity.schemas.migration.service.transform_schema")
    def test_migrates_multiple_event_types(self, mock_transform, migration_service, create_v1_event_type):
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}
        create_v1_event_type("type_1")
        create_v1_event_type("type_2")

        results = migration_service.migrate(["type_1", "type_2"])

        assert len(results) == 2
        assert results[0].event_type_value == "type_1"
        assert results[1].event_type_value == "type_2"

    def test_handles_mixed_success_failure(self, migration_service, v1_event_type):
        results = migration_service.migrate([v1_event_type.value, "nonexistent"])

        assert len(results) == 2
        # First should fail (transform_schema not mocked)
        # Second should fail (not found)
        assert results[1].success is False
        assert "not found" in results[1].errors[0]

    def test_failed_producer_blocks_only_dependent_result(self, migration_service_live):
        producer = MigrationResult(
            event_type_value="producer",
            log=_test_logger.for_event_type("producer"),
            migration_request=MigrationRequest(event_type_value="producer"),
            hardcoded_choices=[],
            resolved_hardcoded_choices=[
                ResolvedHardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    ),
                )
            ],
        )
        dependent = MigrationResult(
            event_type_value="dependent",
            log=_test_logger.for_event_type("dependent"),
            migration_request=MigrationRequest(event_type_value="dependent"),
            hardcoded_choices=[],
            resolved_hardcoded_choices=[
                ResolvedHardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.USE_PROPOSED,
                        choice_field_name="shared_severity",
                    ),
                )
            ],
        )
        independent = MigrationResult(
            event_type_value="independent",
            log=_test_logger.for_event_type("independent"),
            migration_request=MigrationRequest(event_type_value="independent"),
            hardcoded_choices=[],
            resolved_hardcoded_choices=[
                ResolvedHardcodedChoice(
                    property_path=["impact"],
                    choices=[{"value": "high", "display": "High"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["impact"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="independent_impact",
                    ),
                )
            ],
        )

        with (
            patch.object(MigrationService, "build_migration_result", side_effect=[producer, dependent, independent]),
            patch.object(MigrationService, "resolve_and_validate_migration_requests"),
            patch.object(MigrationService, "can_modify_event_type", return_value=True),
            patch.object(MigrationService, "persist_migration") as persist_migration,
        ):

            def persist_side_effect(result, choice_processor):
                if result.event_type_value == "producer":
                    result.errors.append("producer failed")
                    return
                result.metadata["persisted"] = True

            persist_migration.side_effect = persist_side_effect

            results = migration_service_live.migrate(
                [
                    {"event_type_value": "producer"},
                    {"event_type_value": "dependent"},
                    {"event_type_value": "independent"},
                ]
            )

        assert results[0].success is False
        assert any("producer failed" in error for error in results[0].errors)
        assert results[1].success is False
        assert any("dependencies were not persisted successfully" in error for error in results[1].errors)
        assert results[2].success is True
        assert results[2].metadata["persisted"] is True

    def test_rewrite_failure_stays_local_to_single_result(self, migration_service):
        bad_result = MigrationResult(
            event_type_value="bad_result",
            log=_test_logger.for_event_type("bad_result"),
            migration_request=MigrationRequest(event_type_value="bad_result"),
            v2_schema={"json": {"properties": {"severity": {"type": "string", "anyOf": []}}}, "ui": {}},
            hardcoded_choices=[],
            resolved_hardcoded_choices=[
                ResolvedHardcodedChoice(
                    property_path=["missing_field"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["missing_field"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="severity",
                    ),
                )
            ],
        )
        good_result = MigrationResult(
            event_type_value="good_result",
            log=_test_logger.for_event_type("good_result"),
            migration_request=MigrationRequest(event_type_value="good_result"),
            v2_schema={"json": {"properties": {"severity": {"type": "string", "anyOf": []}}}, "ui": {}},
            hardcoded_choices=[],
            resolved_hardcoded_choices=[
                ResolvedHardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "high", "display": "High"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="severity",
                    ),
                )
            ],
        )

        with (
            patch.object(MigrationService, "build_migration_result", side_effect=[bad_result, good_result]),
            patch.object(MigrationService, "resolve_and_validate_migration_requests"),
        ):
            results = migration_service.migrate(
                [
                    {"event_type_value": "bad_result"},
                    {"event_type_value": "good_result"},
                ]
            )

        assert len(results) == 2
        assert results[0].success is False
        assert any("Failed to replace resolved choice reference" in error for error in results[0].errors)
        assert results[1].success is True
        assert results[1].v2_schema["json"]["properties"]["severity"]["anyOf"] == [
            {"$ref": "/api/v2.0/schemas/choices.json?field=severity"}
        ]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestPersistMigration:
    def test_same_result_merge_into_proposed_creates_then_merges(self, migration_service_live, v1_event_type):
        result = MigrationResult(
            event_type_value=v1_event_type.value,
            event_type=v1_event_type,
            v2_schema={
                "json": {
                    "properties": {
                        "severity": {
                            "type": "string",
                            "anyOf": [{"title": "Hardcoded", "oneOf": [{"const": "low", "title": "Low"}]}],
                        },
                        "impact": {
                            "type": "string",
                            "anyOf": [{"title": "Hardcoded", "oneOf": [{"const": "high", "title": "High"}]}],
                        },
                    }
                },
                "ui": {},
            },
            resolved_hardcoded_choices=[
                ResolvedHardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    ),
                ),
                ResolvedHardcodedChoice(
                    property_path=["impact"],
                    choices=[{"value": "high", "display": "High"}],
                    resolution=HardcodedChoiceResolution(
                        property_path=["impact"],
                        strategy=ResolutionStrategy.MERGE_INTO_PROPOSED,
                        choice_field_name="shared_severity",
                        missing_choices=[{"value": "high", "display": "High"}],
                    ),
                ),
            ],
        )

        migration_service_live.persist_migration(result, ChoiceProcessor())

        assert result.success is True
        assert result.metadata["persisted"] is True
        assert list(
            Choice.objects.filter(field="shared_severity").order_by("ordernum").values_list("value", flat=True)
        ) == ["low", "high"]
        assert result.v2_schema["json"]["properties"]["severity"]["anyOf"][0]["$ref"].endswith("?field=shared_severity")
        assert result.v2_schema["json"]["properties"]["impact"]["anyOf"][0]["$ref"].endswith("?field=shared_severity")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestChoiceResolutionAnalysis:
    @patch("activity.schemas.migration.service.transform_schema")
    def test_collects_hardcoded_choices_and_auto_resolution(self, mock_transform, migration_service, v1_event_type):
        mock_transform.return_value = {
            "json": {
                "properties": {
                    "severity": {
                        "title": "Severity",
                        "type": "string",
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "low", "title": "Low"},
                                    {"const": "high", "title": "High"},
                                ],
                            }
                        ],
                    }
                }
            },
            "ui": {},
        }

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is True
        assert len(result.hardcoded_choices) == 1
        hardcoded_choice = result.hardcoded_choices[0]
        assert hardcoded_choice.property_path == ["severity"]
        assert [option.strategy for option in hardcoded_choice.resolution_options] == [ResolutionStrategy.CREATE_NEW]
        assert len(result.resolved_hardcoded_choices) == 1
        assert result.resolved_hardcoded_choices[0].resolution.strategy == ResolutionStrategy.CREATE_NEW

    @patch("activity.schemas.migration.service.transform_schema")
    def test_same_result_overlap_requires_explicit_resolution(self, mock_transform, migration_service, v1_event_type):
        mock_transform.return_value = {
            "json": {
                "properties": {
                    "severity": {
                        "title": "Severity",
                        "type": "string",
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "a", "title": "A"},
                                    {"const": "b", "title": "B"},
                                    {"const": "c", "title": "C"},
                                    {"const": "d", "title": "D"},
                                ],
                            }
                        ],
                    },
                    "impact": {
                        "title": "Impact",
                        "type": "string",
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "b", "title": "B"},
                                    {"const": "c", "title": "C"},
                                    {"const": "d", "title": "D"},
                                ],
                            }
                        ],
                    },
                }
            },
            "ui": {},
        }

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is False
        assert any("Resolution required for property path" in error for error in result.errors)
        assert result.v2_schema is not None
        assert any("oneOf" in option for option in result.v2_schema["json"]["properties"]["severity"]["anyOf"])
        assert any("oneOf" in option for option in result.v2_schema["json"]["properties"]["impact"]["anyOf"])


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestErrorTruncation:
    """Tests for error truncation - migration stops when transform_schema has errors."""

    @patch("activity.schemas.migration.service.transform_schema")
    @patch("activity.schemas.migration.service.LogCollector")
    def test_transform_errors_skip_process_choices(
        self, MockLogCollector, mock_transform, migration_service, v1_event_type
    ):
        """When transform_schema logs errors, process_choices should not run."""
        mock_collector = MockLogCollector.return_value
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}
        mock_collector.get_warnings.return_value = []
        mock_collector.get_errors.return_value = [{"message": "Invalid field mapping"}]
        mock_collector.get_features.return_value = {}

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is False
        assert "Invalid field mapping" in result.errors[0]
        assert result.v2_schema is None
        assert "choices" not in result.metadata

    @patch("activity.schemas.migration.service.transform_schema")
    @patch("activity.schemas.migration.service.LogCollector")
    def test_transform_errors_no_v2_schema(self, MockLogCollector, mock_transform, migration_service, v1_event_type):
        """result.v2_schema remains None when transform has errors."""
        mock_collector = MockLogCollector.return_value
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}
        mock_collector.get_warnings.return_value = [{"message": "Minor issue"}]
        mock_collector.get_errors.return_value = [{"message": "Critical error"}]
        mock_collector.get_features.return_value = {}

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.v2_schema is None
        assert len(result.errors) == 1
        assert len(result.warnings) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEndToEndRewrite:
    """End-to-end tests: migrate_single produces schemas with $ref."""

    @patch("activity.schemas.migration.service.transform_schema")
    def test_migrate_single_rewrites_hardcoded_to_ref(
        self, mock_transform, migration_service, v1_event_type, choices_base_url
    ):
        """Full migrate_single should produce a schema with $ref for hardcoded choices."""
        mock_transform.return_value = {
            "json": {
                "properties": {
                    "severity": {
                        "title": "Severity",
                        "type": "string",
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "low", "title": "Low"},
                                    {"const": "high", "title": "High"},
                                ],
                            }
                        ],
                    },
                    "description": {"type": "string", "title": "Description"},
                }
            },
            "ui": {},
        }

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is True
        assert result.v2_schema is not None
        severity_field = result.v2_schema["json"]["properties"]["severity"]
        # Should be rewritten to $ref
        assert len(severity_field["anyOf"]) == 1
        assert "$ref" in severity_field["anyOf"][0]
        ref_url = severity_field["anyOf"][0]["$ref"]
        assert ref_url.startswith("/api/v2.0/schemas/choices.json?field=")
        assert "choices.json?field=" in ref_url
        # Non-choice field should be untouched
        desc_field = result.v2_schema["json"]["properties"]["description"]
        assert desc_field == {"type": "string", "title": "Description"}

    @patch("activity.schemas.migration.service.transform_schema")
    def test_migrate_single_no_hardcoded_choices_passthrough(self, mock_transform, migration_service, v1_event_type):
        """Schema without hardcoded choices passes through unchanged."""
        clean_schema = {
            "json": {
                "properties": {
                    "name": {"type": "string", "title": "Name"},
                }
            },
            "ui": {},
        }
        mock_transform.return_value = clean_schema

        result = migration_service.migrate([v1_event_type.value])[0]

        assert result.success is True
        assert result.v2_schema == clean_schema

    @patch("activity.schemas.migration.service.transform_schema")
    def test_candidate_field_blocks_migration(
        self, mock_transform, make_migration_service, v1_event_type, create_choice_field
    ):
        """Candidate (partial match) fields should block migration entirely."""
        create_choice_field("severity", [("low", "Low"), ("high", "High")])
        service = make_migration_service()
        mock_transform.return_value = {
            "json": {
                "properties": {
                    "severity": {
                        "title": "Severity",
                        "type": "string",
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "low", "title": "Low"},
                                    {"const": "high", "title": "High"},
                                    {"const": "critical", "title": "Critical"},
                                ],
                            }
                        ],
                    },
                }
            },
            "ui": {},
        }

        result = service.migrate([v1_event_type.value])[0]

        assert result.success is False
        assert any("Resolution required for property path" in e for e in result.errors)
        # Schema is still set for preview purposes
        assert result.v2_schema is not None
        # Candidate field should NOT be rewritten to $ref
        severity = result.v2_schema["json"]["properties"]["severity"]
        assert any("oneOf" in opt for opt in severity["anyOf"])

    @patch("activity.schemas.migration.service.transform_schema")
    @patch.object(MigrationService, "can_modify_event_type", return_value=True)
    def test_candidate_field_prevents_persistence(
        self, mock_perm, mock_transform, make_migration_service, v1_event_type, create_choice_field
    ):
        """Candidate fields should prevent persistence even with dry_run=False."""
        create_choice_field("severity", [("low", "Low"), ("high", "High")])
        service = make_migration_service(dry_run=False)
        mock_transform.return_value = {
            "json": {
                "properties": {
                    "severity": {
                        "title": "Severity",
                        "anyOf": [
                            {
                                "title": "Hardcoded",
                                "type": "string",
                                "oneOf": [
                                    {"const": "low", "title": "Low"},
                                    {"const": "high", "title": "High"},
                                    {"const": "critical", "title": "Critical"},
                                ],
                            }
                        ],
                    },
                }
            },
            "ui": {},
        }

        result = service.migrate([v1_event_type.value])[0]

        assert result.success is False
        # Should NOT persist
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1
