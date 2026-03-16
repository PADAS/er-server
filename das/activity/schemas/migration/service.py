"""
Migration service that orchestrates V1 to V2 schema transformation.

This is the main entry point for migration operations, coordinating:
- Schema transformation via schema_migration_tool
- Post-processing (choice conversion, URL updates)
- Result collection with warnings/errors
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from schema_migration_tool import LogCollector, transform_schema
from schema_migration_tool.batch.normalize_export import preprocess_template_vars

from django.db import transaction

from activity.models import EventType
from activity.permissions import EventCategoryPermissions
from choices.models import Choice

from .choice_processor import (
    ChoiceProcessor,
    HardcodedChoice,
    HardcodedChoiceResolution,
)

logger = logging.getLogger(__name__)


@dataclass
class MigrationRequest:
    event_type_value: str
    hardcoded_choices_resolutions: Optional[List[HardcodedChoiceResolution]] = None

    @classmethod
    def _normalize_resolution(cls, data: HardcodedChoiceResolution | dict) -> HardcodedChoiceResolution:
        if isinstance(data, HardcodedChoiceResolution):
            return data
        return HardcodedChoiceResolution.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "MigrationRequest":
        normalized_data = data.copy()

        if "event_type" in normalized_data and "event_type_value" not in normalized_data:
            normalized_data["event_type_value"] = normalized_data.pop("event_type")

        if "hardcoded_choices_resolutions" in normalized_data and normalized_data["hardcoded_choices_resolutions"]:
            normalized_data["hardcoded_choices_resolutions"] = [
                cls._normalize_resolution(item) for item in normalized_data["hardcoded_choices_resolutions"]
            ]

        return cls(**normalized_data)

    @classmethod
    def from_input(cls, data: "MigrationRequest | str | Dict[str, Any]") -> "MigrationRequest":
        if isinstance(data, cls):
            return data

        if isinstance(data, str):
            return cls(event_type_value=data)

        if isinstance(data, dict):
            return cls.from_dict(data)

        raise TypeError("MigrationRequest input must be a MigrationRequest, str, or dict")


@dataclass
class MigrationResult:
    """Result of migrating a single EventType."""

    event_type_value: str
    event_type: Optional[EventType] = None
    migration_request: Optional[MigrationRequest] = None
    v2_schema: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    hardcoded_choices: Optional[List[HardcodedChoice]] = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        # TODO: add hardcoded_choices to the result
        return {
            "event_type": self.event_type_value,
            "v2_schema": self.v2_schema,
            "warnings": self.warnings,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class MigrationService:
    """Orchestrates V1 → V2 EventType schema migration.

    Two-phase: analyze all event types first, then persist atomically.
    """

    def __init__(self, request, dry_run: bool = True):
        self.request = request
        self.dry_run = dry_run
        self.existing_choices: Dict[str, List[str]] = {}
        self.proposed_choices: Dict[str, List[str]] = {}

    def get_existing_choice_fields(self) -> Dict[str, List[str]]:
        fields: Dict[str, List[str]] = {}
        choices = Choice.objects.filter(model=Choice.EVENT_MODEL, is_active=True).values_list("field", "value")

        for field_name, value in choices:
            if field_name not in fields:
                fields[field_name] = []
            fields[field_name].append(value)

        return fields

    def index_selected_resolutions(self, result: MigrationResult) -> Dict[tuple[str, ...], HardcodedChoiceResolution]:
        selected_resolutions: Dict[tuple[str, ...], HardcodedChoiceResolution] = {}

        if not result.migration_request.hardcoded_choices_resolutions:
            return selected_resolutions

        for resolution in result.migration_request.hardcoded_choices_resolutions:
            if not resolution.property_path:
                result.errors.append("Hardcoded choice resolution is missing property_path")
                continue

            property_path = tuple(resolution.property_path)
            if property_path in selected_resolutions:
                result.errors.append(
                    f"Duplicate hardcoded choice resolution for property path: {resolution.property_path}"
                )
                continue

            selected_resolutions[property_path] = resolution

        return selected_resolutions

    def validate_selected_resolutions(
        self,
        result: MigrationResult,
        selected_resolutions: Dict[tuple[str, ...], HardcodedChoiceResolution],
        hardcoded_choices_by_path: Dict[tuple[str, ...], HardcodedChoice],
        choice_processor: ChoiceProcessor,
    ) -> None:
        for property_path, resolution in selected_resolutions.items():
            hardcoded_choice = hardcoded_choices_by_path.get(property_path)
            if hardcoded_choice is None:
                result.errors.append(f"Unknown hardcoded choice resolution property path: {resolution.property_path}")
                continue

            if choice_processor.find_matching_resolution_option(hardcoded_choice, resolution) is None:
                result.errors.append(
                    f"Invalid resolution for property path {resolution.property_path}: "
                    f"{resolution.strategy} -> {resolution.choice_field_name}"
                )

    def validate_required_resolutions(
        self,
        result: MigrationResult,
        selected_resolutions: Dict[tuple[str, ...], HardcodedChoiceResolution],
    ) -> None:
        for hardcoded_choice in result.hardcoded_choices:
            if tuple(hardcoded_choice.property_path) in selected_resolutions:
                continue

            try:
                if hardcoded_choice.needs_resolution():
                    result.errors.append(f"Resolution required for property path: {hardcoded_choice.property_path}")
            except ValueError as exc:
                result.errors.append(f"{hardcoded_choice.property_path}: {exc}")

    def validate_migration_requests(self, results: List[MigrationResult], choice_processor: ChoiceProcessor) -> None:
        for result in results:
            if not result.success or not result.hardcoded_choices:
                continue

            selected_resolutions = self.index_selected_resolutions(result)
            hardcoded_choices_by_path = {tuple(choice.property_path): choice for choice in result.hardcoded_choices}
            self.validate_selected_resolutions(
                result,
                selected_resolutions,
                hardcoded_choices_by_path,
                choice_processor,
            )
            self.validate_required_resolutions(result, selected_resolutions)

    def get_v1_event_types(self) -> List[str]:
        """Get all V1 EventType values."""
        return list(
            EventType.objects.filter(version=EventType.VersionChoices.VERSION_1).values_list("value", flat=True)
        )

    def migrate(self, migration_requests: List[str | dict]) -> List[MigrationResult]:
        """Migrate multiple EventTypes. Atomic per EventType: each commits or rolls back independently."""
        results: list[MigrationResult] = []

        if len(migration_requests) == 0:
            # Just a practical shortcut: if no "migration requests" provided, just do a dry run of all V1 event types
            self.dry_run = True
            migration_requests = self.get_v1_event_types()

        # Normalize migration requests to MigrationRequest objects
        migration_requests = [MigrationRequest.from_input(item) for item in migration_requests]

        # Phase 1: Transform all v1 schemas to v2, gathering info about hardcoded choices
        for et_mr in migration_requests:
            result = self.collect_info(et_mr)
            results.append(result)

        # Phase 2: Analyze hardcoded choices and determine possible resolutions for all
        self.existing_choices = self.get_existing_choice_fields()
        self.proposed_choices = {}
        choice_processor = ChoiceProcessor()
        choice_processor.analyze_migration_results(results, self.existing_choices, self.proposed_choices)

        # Phase 3: Validate migration requests and prepare for persistence
        self.validate_migration_requests(results, choice_processor)

        if self.dry_run:
            return results
        # Phase 3: Persistence (only if not dry run)
        # We build a data structure that holds what choices have been successfully created
        # So we know how to handle the ones that may depend on them

        # Atomic persist for each event type schema and it's associated choices while respecting dependencies
        for result in results:
            if not result.success:
                continue

            with transaction.atomic():
                self.persist_migration(result, choice_processor)
                if not result.success:
                    transaction.set_rollback(True)

        return results

    def collect_info(self, migration_request: MigrationRequest) -> MigrationResult:
        """
        First pass: Get event type, get current schema, transform to V2, look for hardcoded choices.
        """
        result = MigrationResult(
            event_type_value=migration_request.event_type_value,
            migration_request=migration_request,
        )

        try:
            event_type = EventType.objects.get(value=migration_request.event_type_value)
        except EventType.DoesNotExist:
            result.errors.append(f"EventType '{migration_request.event_type_value}' not found")
            return result

        # Check authorization
        if not self.can_modify_event_type(event_type) and not self.dry_run:
            result.errors.append(f"Permission denied for EventType '{migration_request.event_type_value}'")
            return result

        result.event_type = event_type

        if event_type.version != EventType.VersionChoices.VERSION_1:
            result.errors.append(f"EventType '{migration_request.event_type_value}' is not V1")
            return result

        # Transform schema
        self.transform_schema(result)
        if not result.success:
            return result

        result.hardcoded_choices = ChoiceProcessor().get_hardcoded_choices(result.v2_schema)
        return result

    def transform_schema(self, result: MigrationResult):
        """Transform V1 schema to V2 schema and collect transformation metadata.

        Args:
            result (MigrationResult): Migration result to update with transformed schema and metadata.
        """
        log_collector = LogCollector({"event_type": result.event_type.value})

        try:
            v1_schema = json.loads(preprocess_template_vars(result.event_type.schema))
        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON in schema: {e}")
            return

        result.v2_schema = transform_schema(v1_schema, log_collector)

        # Collect warnings/errors from transformation
        for warning in log_collector.get_warnings():
            result.warnings.append(warning.get("message"))

        for error in log_collector.get_errors():
            result.errors.append(error.get("message"))

        # Store transformation metadata
        features = log_collector.get_features()
        result.metadata["ignored_properties"] = features.get("ignoredProperties", [])
        result.metadata["unsupported_features"] = features.get("unsupportedFeatures", [])

        if len(result.metadata["unsupported_features"]) > 0:
            result.errors.append("Unsupported features found in schema: look at metadata for details")

    def persist_migration(self, result: MigrationResult, choice_processor: ChoiceProcessor) -> None:
        """
        Persist the migrated schema and its hardcoded choices. For each hardcoded choice,
        we will follow the user specified or default behavior in HardcodedChoiceResolution.

        Args:
            result (MigrationResult): Migration result containing the migrated schema and choices.
        """
        if not result.success:
            return

        event_type = result.event_type

        try:
            choice_processor.persist_hardcoded_choices(event_type, result)
            event_type.schema = json.dumps(result.v2_schema, indent=2)
            event_type.version = EventType.VersionChoices.VERSION_2
            event_type.save(update_fields=["schema", "version", "updated_at"])
        except Exception as e:
            result.errors.append(f"Failed to persist migration: {e}")
            return

        result.metadata["persisted"] = True

    def can_modify_event_type(self, event_type: EventType) -> bool:
        # Simulate PATCH to reuse DRF object-level permission check
        original_method = self.request.method
        try:
            self.request.method = "PATCH"
            permission = EventCategoryPermissions()
            return permission.has_object_permission(self.request, view=None, obj=event_type)
        finally:
            self.request.method = original_method
