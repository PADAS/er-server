"""Tests for MigrationService - schema migration orchestration.
"""

from unittest.mock import patch

import pytest

from activity.models import EventType
from activity.schemas.migration.service import MigrationResult, MigrationService
from choices.models import Choice


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_success_when_no_errors(self):
        result = MigrationResult(event_type="test")
        assert result.success is True

    def test_failure_when_errors_present(self):
        result = MigrationResult(event_type="test", errors=["Something failed"])
        assert result.success is False

    def test_to_dict(self):
        result = MigrationResult(
            event_type="test",
            v2_schema={"json": {}},
            warnings=["Warning 1"],
            metadata={"key": "value"},
        )
        d = result.to_dict()
        assert d["event_type"] == "test"
        assert d["v2_schema"] == {"json": {}}
        assert d["warnings"] == ["Warning 1"]
        assert d["errors"] == []
        assert d["metadata"] == {"key": "value"}


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
    """Tests for migrate_single method."""

    def test_event_type_not_found(self, migration_service):
        result = migration_service.migrate_single("nonexistent_type")

        assert result.success is False
        assert "not found" in result.errors[0]

    def test_skips_v2_event_type(self, migration_service, v2_event_type):
        result = migration_service.migrate_single(v2_event_type.value)

        assert result.success is False
        assert "not V1" in result.errors[0]

    @patch("activity.schemas.migration.service.transform_schema")
    def test_dry_run_does_not_persist(self, mock_transform, migration_service, v1_event_type):
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}

        result = migration_service.migrate_single(v1_event_type.value)

        assert result.success is True
        # Reload from DB - should still be V1
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1

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
class TestAuthorization:
    """Tests for authorization checks."""

    @patch.object(MigrationService, "can_modify_event_type", return_value=False)
    @patch("activity.schemas.migration.service.transform_schema")
    def test_denies_when_no_permission(self, mock_transform, mock_perm, migration_service_live, v1_event_type):
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}

        result = migration_service_live.migrate_single(v1_event_type.value)

        assert result.success is False
        assert "Permission denied" in result.errors[0]

    @patch.object(MigrationService, "can_modify_event_type", return_value=False)
    @patch("activity.schemas.migration.service.transform_schema")
    def test_allows_dry_run_without_permission(self, mock_transform, mock_perm, migration_service, v1_event_type):
        """Dry run should work even without modify permission."""
        mock_transform.return_value = {"json": {"properties": {}}, "ui": {}}

        result = migration_service.migrate_single(v1_event_type.value)

        assert result.success is True


@pytest.mark.django_db
class TestPersistChoices:
    """Tests for persist_choices method."""

    def test_creates_new_choice_field(self, migration_service_live, hardcoded_values, migration_result_with_choices):
        values = hardcoded_values(("high", "High"), ("low", "Low"))
        result = migration_result_with_choices(
            [{"field_name": "priority", "status": "to_create", "proposed_name": "test_priority", "values": values}]
        )

        migration_service_live.persist_choices(result)

        # Check Choice objects were created
        choices = Choice.objects.filter(field="test_priority").order_by("ordernum")
        assert choices.count() == 2
        assert choices[0].value == "high"
        assert choices[1].value == "low"
        # Check status was updated
        field_info = result.metadata["choices"]["fields"][0]
        assert field_info["status"] == "created"
        assert field_info["existing_choice_field"] == "test_priority"

    def test_skips_non_to_create_fields(self, migration_service_live, migration_result_with_choices):
        """persist_choices only handles to_create status; other statuses are ignored."""
        result = migration_result_with_choices(
            [{"field_name": "status", "status": "matched", "existing_choice_field": "status"}]
        )

        # Should not raise
        migration_service_live.persist_choices(result)

    def test_reuses_choice_field_for_similar_values(
        self, migration_service_live, hardcoded_values, migration_result_with_choices
    ):
        """Test that multiple fields with same values reuse one choice field."""
        values = hardcoded_values(("high", "High"), ("low", "Low"))
        result = migration_result_with_choices(
            [
                {
                    "field_name": "priority1",
                    "status": "to_create",
                    "proposed_name": "priority_options",
                    "values": values,
                },
                {
                    "field_name": "priority2",
                    "status": "to_create",
                    "proposed_name": "priority_options_2",
                    "values": values,
                },
            ]
        )

        migration_service_live.persist_choices(result)

        # First field should be created
        field1 = result.metadata["choices"]["fields"][0]
        assert field1["status"] == "created"
        assert field1["existing_choice_field"] == "priority_options"

        # Second field should reuse the first
        field2 = result.metadata["choices"]["fields"][1]
        assert field2["status"] == "reused"
        assert field2["existing_choice_field"] == "priority_options"

        # Only one set of choices should exist
        assert Choice.objects.filter(field="priority_options").count() == 2
        assert Choice.objects.filter(field="priority_options_2").count() == 0

    def test_no_fields_does_nothing(self, migration_service_live, migration_result_with_choices):
        result = migration_result_with_choices([])

        # Should not raise
        migration_service_live.persist_choices(result)


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
        assert results[0].event_type == "type_1"
        assert results[1].event_type == "type_2"

    def test_handles_mixed_success_failure(self, migration_service, v1_event_type):
        results = migration_service.migrate([v1_event_type.value, "nonexistent"])

        assert len(results) == 2
        # First should fail (transform_schema not mocked)
        # Second should fail (not found)
        assert results[1].success is False
        assert "not found" in results[1].errors[0]


@pytest.mark.django_db
class TestProcessChoices:
    """Tests for process_choices method."""

    def test_processes_hardcoded_choices_in_schema(self, migration_service, v2_schema_with_fields, migration_result):
        v2_schema = v2_schema_with_fields({"severity": [("low", "Low"), ("high", "High")]})
        result = migration_result()

        migration_service.process_choices(v2_schema, result)

        assert "choices" in result.metadata
        assert len(result.metadata["choices"]["fields"]) == 1
        field_info = result.metadata["choices"]["fields"][0]
        assert field_info["field_name"] == "severity"
        assert field_info["status"] == "to_create"

    def test_no_hardcoded_choices(self, migration_service, v2_schema_with_fields, migration_result):
        v2_schema = v2_schema_with_fields({"name": {"type": "string"}})
        result = migration_result()

        migration_service.process_choices(v2_schema, result)

        assert result.metadata["choices"]["fields"] == []

    def test_candidate_fields_produce_errors(
        self, migration_service, create_choice_field, v2_schema_with_fields, migration_result
    ):
        """Candidate (partial match) fields should add errors to block migration."""
        create_choice_field("status", [("open", "Open"), ("closed", "Closed")])
        v2_schema = v2_schema_with_fields({"status": [("open", "Open"), ("closed", "Closed"), ("pending", "Pending")]})
        result = migration_result()

        migration_service.process_choices(v2_schema, result)

        assert not result.success
        assert len(result.errors) == 1
        assert "partial match" in result.errors[0]
        assert "Cannot auto-migrate" in result.errors[0]

    def test_matched_fields_do_not_produce_errors(
        self, migration_service, create_choice_field, v2_schema_with_fields, migration_result
    ):
        """100% matched fields should not produce errors."""
        create_choice_field("priority", [("high", "High"), ("low", "Low")])
        v2_schema = v2_schema_with_fields({"priority": [("high", "High"), ("low", "Low")]})
        result = migration_result()

        migration_service.process_choices(v2_schema, result)

        assert result.success
        assert len(result.errors) == 0

    def test_to_create_fields_do_not_produce_errors(self, migration_service, v2_schema_with_fields, migration_result):
        """No-match fields (to_create) should not produce errors."""
        v2_schema = v2_schema_with_fields({"severity": [("low", "Low"), ("high", "High")]})
        result = migration_result()

        migration_service.process_choices(v2_schema, result)

        assert result.success
        assert len(result.errors) == 0
        assert result.metadata["choices"]["fields"][0]["status"] == "to_create"

    def test_batch_conflict_subset_blocks_migration(self, migration_service, v2_schema_with_fields, migration_result):
        """Field B (b,c,d) is a subset of Field A (a,b,c,d) — Jaccard 3/4=0.75 ≥ 2/3."""
        v2_schema = v2_schema_with_fields(
            {
                "severity": [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                "impact": [("b", "B"), ("c", "C"), ("d", "D")],
            }
        )
        result = migration_result()

        migration_service.process_choices(v2_schema, result, proposed_choices={})

        assert not result.success
        assert any("partial match" in e for e in result.errors)

    def test_batch_conflict_superset_blocks_migration(self, migration_service, v2_schema_with_fields, migration_result):
        """Field C (a,b,c,d,e) is a superset of Field A (a,b,c,d) — Jaccard 4/5=0.80 ≥ 2/3."""
        v2_schema = v2_schema_with_fields(
            {
                "severity": [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                "full_severity": [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D"), ("e", "E")],
            }
        )
        result = migration_result()

        migration_service.process_choices(v2_schema, result, proposed_choices={})

        assert not result.success
        assert any("partial match" in e for e in result.errors)

    def test_batch_no_conflict_below_threshold(self, migration_service, v2_schema_with_fields, migration_result):
        """Fields with low overlap (Jaccard 1/7=0.14 < 2/3) should not block."""
        v2_schema = v2_schema_with_fields(
            {
                "field_a": [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                "field_b": [("d", "D"), ("e", "E"), ("f", "F"), ("g", "G")],
            }
        )
        result = migration_result()

        migration_service.process_choices(v2_schema, result, proposed_choices={})

        assert result.success

    def test_batch_exact_duplicate_values_allowed(self, migration_service, v2_schema_with_fields, migration_result):
        """Exact same values (Jaccard=1.0) are allowed — handled by persist_choices dedup."""
        v2_schema = v2_schema_with_fields(
            {
                "field_a": [("a", "A"), ("b", "B")],
                "field_b": [("a", "A"), ("b", "B")],
            }
        )
        result = migration_result()

        migration_service.process_choices(v2_schema, result, proposed_choices={})

        assert result.success

    def test_batch_conflict_schema_not_rewritten_to_ref(
        self, migration_service, v2_schema_with_fields, migration_result
    ):
        """Conflicting fields should keep hardcoded values (not rewritten to $ref)."""
        v2_schema = v2_schema_with_fields(
            {
                "severity": [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                "impact": [("b", "B"), ("c", "C"), ("d", "D")],
            }
        )
        result = migration_result()

        migration_service.process_choices(v2_schema, result, proposed_choices={})

        # Both fields should still have hardcoded oneOf structure
        for field_name in ("severity", "impact"):
            field_schema = v2_schema["json"]["properties"][field_name]
            assert any("oneOf" in opt for opt in field_schema["anyOf"])


class TestGetValuesKey:
    """Tests for _get_values_key helper method."""

    def test_generates_consistent_key(self, migration_service, choice_processor, hardcoded_values):
        values = hardcoded_values(("b_value", "B"), ("a_value", "A"))

        key = migration_service._get_values_key(values, choice_processor)

        # Should be sorted and normalized
        assert key == "a-value|b-value"

    def test_normalizes_for_comparison(self, migration_service, choice_processor):
        values1 = [{"value": "High_Priority", "display": "High"}]
        values2 = [{"value": "high-priority", "display": "High"}]

        key1 = migration_service._get_values_key(values1, choice_processor)
        key2 = migration_service._get_values_key(values2, choice_processor)

        assert key1 == key2


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

        result = migration_service.migrate_single(v1_event_type.value)

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

        result = migration_service.migrate_single(v1_event_type.value)

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

        result = migration_service.migrate_single(v1_event_type.value)

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

        result = migration_service.migrate_single(v1_event_type.value)

        assert result.success is True
        assert result.v2_schema == clean_schema

    @patch("activity.schemas.migration.service.transform_schema")
    def test_candidate_field_blocks_migration(
        self, mock_transform, migration_service, v1_event_type, create_choice_field
    ):
        """Candidate (partial match) fields should block migration entirely."""
        create_choice_field("severity", [("low", "Low"), ("high", "High")])
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

        result = migration_service.migrate_single(v1_event_type.value)

        assert result.success is False
        assert any("Cannot auto-migrate" in e for e in result.errors)
        # Schema is still set for preview purposes
        assert result.v2_schema is not None
        # Candidate field should NOT be rewritten to $ref
        severity = result.v2_schema["json"]["properties"]["severity"]
        assert any("oneOf" in opt for opt in severity["anyOf"])

    @patch("activity.schemas.migration.service.transform_schema")
    @patch.object(MigrationService, "can_modify_event_type", return_value=True)
    def test_candidate_field_prevents_persistence(
        self, mock_perm, mock_transform, migration_service_live, v1_event_type, create_choice_field
    ):
        """Candidate fields should prevent persistence even with dry_run=False."""
        create_choice_field("severity", [("low", "Low"), ("high", "High")])
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

        result = migration_service_live.migrate_single(v1_event_type.value)

        assert result.success is False
        # Should NOT persist
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1
