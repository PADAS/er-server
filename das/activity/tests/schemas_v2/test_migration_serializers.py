from activity.schemas.migration.choice_processor import (
    HardcodedChoice,
    HardcodedChoiceResolution,
    ResolutionStrategy,
)
from activity.schemas.migration.logger import LogContext, MigrationLogger
from activity.schemas.migration.service import MigrationResult
from activity.serializers.event_types_v2 import (
    MigrationEventTypeRequestItemSerializer,
    MigrationRequestSerializer,
    MigrationResultSerializer,
)

_test_context = LogContext(migration_request_id="MR-test", tenant_name="test", dry_run=True)
_test_logger = MigrationLogger(context=_test_context)


class TestMigrationSerializerContracts:
    def test_migration_request_serializer_normalizes_string_event_types_and_defaults_dry_run(self):
        serializer = MigrationRequestSerializer(data={"event_types": ["fire_rep"]})

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["dry_run"] is True
        assert serializer.validated_data["event_types"][0]["event_type_value"] == "fire_rep"

    def test_migration_request_serializer_rejects_empty_event_types_when_not_dry_run(self):
        serializer = MigrationRequestSerializer(data={"dry_run": False, "event_types": []})

        assert serializer.is_valid() is False
        assert serializer.errors["event_types"] == ["This list may not be empty when dry_run is false."]

    def test_migration_request_serializer_rejects_duplicate_event_type_values(self):
        serializer = MigrationRequestSerializer(
            data={
                "dry_run": False,
                "event_types": [
                    "fire_rep",
                    {
                        "event_type_value": "fire_rep",
                        "hardcoded_choices_resolutions": [
                            {
                                "property_path": ["severity"],
                                "strategy": "USE_EXISTING",
                                "choice_field_name": "severity",
                            }
                        ],
                    },
                ],
            }
        )

        assert serializer.is_valid() is False
        assert serializer.errors["event_types"] == ["Duplicate event_type_value entries are not allowed: fire_rep."]

    def test_migration_event_type_request_item_serializer_requires_event_type_value(self):
        serializer = MigrationEventTypeRequestItemSerializer(data={"hardcoded_choices_resolutions": []})

        assert serializer.is_valid() is False
        assert serializer.errors["non_field_errors"] == ["event_type_value is required."]

    def test_migration_request_serializer_requires_property_path_in_resolution_requests(self):
        serializer = MigrationRequestSerializer(
            data={
                "event_types": [
                    {
                        "event_type_value": "fire_rep",
                        "hardcoded_choices_resolutions": [
                            {
                                "strategy": "USE_EXISTING",
                                "choice_field_name": "severity",
                            }
                        ],
                    }
                ]
            }
        )

        assert serializer.is_valid() is False
        assert serializer.errors["event_types"][0]["hardcoded_choices_resolutions"][0]["property_path"] == [
            "This field is required."
        ]

    def test_migration_request_serializer_accepts_structured_resolution_requests(self):
        serializer = MigrationRequestSerializer(
            data={
                "dry_run": False,
                "event_types": [
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
                ],
            }
        )

        assert serializer.is_valid(), serializer.errors
        resolution = serializer.validated_data["event_types"][0]["hardcoded_choices_resolutions"][0]
        assert serializer.validated_data["dry_run"] is False
        assert resolution["property_path"] == ["severity"]
        assert resolution["strategy"] == "USE_EXISTING"
        assert resolution["choice_field_name"] == "severity"

    def test_migration_result_serializer_serializes_nested_hardcoded_choices(self):
        serializer = MigrationResultSerializer(
            MigrationResult(
                event_type_value="fire_rep",
                log=_test_logger.for_event_type("fire_rep"),
                v2_schema={"json": {"properties": {}}},
                warnings=[],
                errors=[],
                metadata={"ignored_properties": []},
                hardcoded_choices=[
                    HardcodedChoice(
                        property_path=["severity"],
                        choices=[{"value": "minor", "display": "Minor"}],
                        resolution_options=[
                            HardcodedChoiceResolution(
                                property_path=["severity"],
                                strategy=ResolutionStrategy.CREATE_NEW,
                                choice_field_name="severity",
                            )
                        ],
                    )
                ],
            )
        )

        assert serializer.data["event_type"] == "fire_rep"
        assert serializer.data["hardcoded_choices"][0]["property_path"] == ["severity"]
        assert serializer.data["hardcoded_choices"][0]["choices"] == [{"value": "minor", "display": "Minor"}]
        assert serializer.data["hardcoded_choices"][0]["resolution_options"][0]["strategy"] == "CREATE_NEW"
        assert serializer.data["hardcoded_choices"][0]["resolution_options"][0]["choice_field_name"] == "severity"
