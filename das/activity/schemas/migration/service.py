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
from django.db.models import QuerySet

from activity.models import EventType
from activity.permissions import EventCategoryPermissions
from choices.models import Choice

from .choice_processor import (
    ChoiceProcessor,
    HardcodedChoice,
    HardcodedChoiceResolution,
    ResolutionStrategy,
    get_field_schema_from_prop_path,
    rewrite_field_to_ref,
)
from .logger import ErrorCode, EventTypeMigrationLogger, MigrationLogger

logger = logging.getLogger(__name__)


@dataclass
class MigrationRequest:
    event_type_value: str
    hardcoded_choices_resolutions: Optional[List[HardcodedChoiceResolution]] = None
    event_type: Optional[EventType] = None

    @classmethod
    def _normalize_resolution(cls, data: HardcodedChoiceResolution | dict) -> HardcodedChoiceResolution:
        if isinstance(data, HardcodedChoiceResolution):
            return data
        return HardcodedChoiceResolution.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "MigrationRequest":
        normalized_data = data.copy()

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
class ResolvedHardcodedChoice:
    property_path: List[str]
    choices: List[Dict[str, str]]
    resolution: HardcodedChoiceResolution


@dataclass
class MigrationResult:
    """Result of migrating a single EventType."""

    event_type_value: str = ""
    log: EventTypeMigrationLogger | None = field(repr=False, default=None)
    event_type: Optional[EventType] = None
    migration_request: Optional[MigrationRequest] = None
    v2_schema: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    hardcoded_choices: Optional[List[HardcodedChoice]] = None
    resolved_hardcoded_choices: Optional[List[ResolvedHardcodedChoice]] = None

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

    def __init__(
        self,
        *,
        request,
        dry_run: bool = True,
        queryset: Optional[QuerySet] = None,
        logger: MigrationLogger | None = None,
    ):
        self.request = request
        self._queryset = queryset
        self.dry_run = dry_run
        self.existing_choices: Dict[str, List[str]] = {}
        self.proposed_choices: Dict[str, List[str]] = {}
        self.logger: MigrationLogger = logger or MigrationLogger.from_request(request, dry_run=dry_run)

    def get_queryset(self) -> QuerySet[EventType]:
        if self._queryset is not None:
            return self._queryset

        self._queryset = EventType.objects.filter(
            category__is_active=True,  # Always filter out inactive categories.
        ).select_related("category")

        return self._queryset

    def load_existing_choice_fields(self) -> Dict[str, List[str]]:
        """
        Get existing choice fields from the database.
        """
        fields: Dict[str, List[str]] = {}
        choices = Choice.objects.filter(model=Choice.EVENT_MODEL, is_active=True).values_list("field", "value")

        for field_name, value in choices:
            if field_name not in fields:
                fields[field_name] = []
            fields[field_name].append(value)

        return fields

    def index_selected_resolutions(self, result: MigrationResult) -> Dict[tuple[str, ...], HardcodedChoiceResolution]:
        """
        Index selected resolutions by property path (as tuple) for quick lookup.
        """
        selected_resolutions: Dict[tuple[str, ...], HardcodedChoiceResolution] = {}

        if not result.migration_request or not result.migration_request.hardcoded_choices_resolutions:
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

    def get_effective_resolution(
        self,
        hardcoded_choice: HardcodedChoice,
        selected_resolutions: Dict[tuple[str, ...], HardcodedChoiceResolution],
        choice_processor: ChoiceProcessor,
    ) -> HardcodedChoiceResolution | None:
        property_path = tuple(hardcoded_choice.property_path)
        selected_resolution = selected_resolutions.get(property_path)

        if selected_resolution is None:
            try:
                if hardcoded_choice.needs_resolution():
                    return None
            except ValueError:
                return None

            option = hardcoded_choice.resolution_options[0]
            return HardcodedChoiceResolution(
                strategy=option.strategy,
                choice_field_name=option.choice_field_name,
                missing_choices=option.missing_choices,
                property_path=list(option.property_path or hardcoded_choice.property_path),
            )

        matched_option = choice_processor.find_matching_resolution_option(hardcoded_choice, selected_resolution)
        if matched_option is None:
            return None

        return HardcodedChoiceResolution(
            strategy=selected_resolution.strategy,
            choice_field_name=selected_resolution.choice_field_name or matched_option.choice_field_name,
            missing_choices=matched_option.missing_choices,
            property_path=list(selected_resolution.property_path or matched_option.property_path or property_path),
        )

    def build_resolved_hardcoded_choices(
        self,
        result: MigrationResult,
        selected_resolutions: Dict[tuple[str, ...], HardcodedChoiceResolution],
        choice_processor: ChoiceProcessor,
    ) -> List["ResolvedHardcodedChoice"]:
        resolved_hardcoded_choices: List[ResolvedHardcodedChoice] = []

        for hardcoded_choice in result.hardcoded_choices or []:
            effective_resolution = self.get_effective_resolution(
                hardcoded_choice,
                selected_resolutions,
                choice_processor,
            )
            if effective_resolution is None:
                continue

            resolved_hardcoded_choices.append(
                ResolvedHardcodedChoice(
                    property_path=list(hardcoded_choice.property_path),
                    choices=hardcoded_choice.choices,
                    resolution=effective_resolution,
                )
            )

        return resolved_hardcoded_choices

    def validate_and_index_create_new_targets(
        self,
        results: List[MigrationResult],
    ) -> Dict[str, int]:
        create_new_targets: Dict[str, int] = {}

        for result_index, result in enumerate(results):
            if not result.success or not result.resolved_hardcoded_choices:
                continue

            for resolved_choice in result.resolved_hardcoded_choices:
                resolution = resolved_choice.resolution
                if resolution.strategy != ResolutionStrategy.CREATE_NEW:
                    continue

                choice_field_name = resolution.choice_field_name
                if not choice_field_name:
                    result.errors.append(
                        f"CREATE_NEW resolution is missing choice_field_name for property path: "
                        f"{resolved_choice.property_path}"
                    )
                    continue

                if choice_field_name in self.existing_choices:
                    result.errors.append(
                        f"Choice field '{choice_field_name}' already exists and cannot be created again"
                    )
                    continue

                if choice_field_name in create_new_targets:
                    result.errors.append(
                        f"Choice field '{choice_field_name}' is already planned for creation in this batch"
                    )
                    continue

                create_new_targets[choice_field_name] = result_index

        return create_new_targets

    def validate_resolution_dependencies(
        self,
        results: List[MigrationResult],
        create_new_targets: Dict[str, int],
    ) -> None:
        for result_index, result in enumerate(results):
            if not result.success or not result.resolved_hardcoded_choices:
                continue

            for resolved_choice in result.resolved_hardcoded_choices:
                resolution = resolved_choice.resolution
                choice_field_name = resolution.choice_field_name

                if resolution.strategy not in (
                    ResolutionStrategy.USE_PROPOSED,
                    ResolutionStrategy.MERGE_INTO_PROPOSED,
                ):
                    continue

                producer_index = create_new_targets.get(choice_field_name)
                if producer_index is None:
                    result.errors.append(
                        f"Proposed choice field '{choice_field_name}' is not planned for creation in this batch"
                    )
                    continue

                if producer_index > result_index:
                    result.errors.append(
                        f"Proposed choice field '{choice_field_name}' is created by a later migration request"
                    )
                    continue

                producer_result = results[producer_index]
                if not producer_result.success:
                    result.errors.append(
                        f"Proposed choice field '{choice_field_name}' depends on an invalid migration request"
                    )

    def resolve_and_validate_migration_requests(
        self,
        results: List[MigrationResult],
        choice_processor: ChoiceProcessor,
    ) -> None:
        selected_resolutions_by_result: Dict[int, Dict[tuple[str, ...], HardcodedChoiceResolution]] = {}

        for result in results:
            if not result.success or not result.hardcoded_choices:
                continue

            selected_resolutions = self.index_selected_resolutions(result)
            selected_resolutions_by_result[id(result)] = selected_resolutions
            hardcoded_choices_by_path = {tuple(choice.property_path): choice for choice in result.hardcoded_choices}
            self.validate_selected_resolutions(
                result,
                selected_resolutions,
                hardcoded_choices_by_path,
                choice_processor,
            )
            self.validate_required_resolutions(result, selected_resolutions)

        for result in results:
            if not result.success or not result.hardcoded_choices:
                continue

            result.resolved_hardcoded_choices = self.build_resolved_hardcoded_choices(
                result,
                selected_resolutions_by_result.get(id(result), {}),
                choice_processor,
            )

        create_new_targets = self.validate_and_index_create_new_targets(results)
        self.validate_resolution_dependencies(results, create_new_targets)

    def get_created_choice_field_names(self, result: MigrationResult) -> set[str]:
        return {
            resolved_choice.resolution.choice_field_name
            for resolved_choice in result.resolved_hardcoded_choices or []
            if resolved_choice.resolution.strategy == ResolutionStrategy.CREATE_NEW
        }

    def can_persist_result(
        self,
        result: MigrationResult,
        persisted_choice_fields: set[str],
    ) -> bool:
        local_created_fields = self.get_created_choice_field_names(result)
        blocked_fields = sorted(
            {
                resolved_choice.resolution.choice_field_name
                for resolved_choice in result.resolved_hardcoded_choices or []
                if resolved_choice.resolution.strategy
                in (
                    ResolutionStrategy.USE_PROPOSED,
                    ResolutionStrategy.MERGE_INTO_PROPOSED,
                )
                and resolved_choice.resolution.choice_field_name not in local_created_fields
                and resolved_choice.resolution.choice_field_name not in persisted_choice_fields
            }
        )

        if not blocked_fields:
            return True

        result.errors.append(
            f"Proposed choice field dependencies were not persisted successfully: {', '.join(blocked_fields)}"
        )
        return False

    def rewrite_resolved_choice_refs(self, result: MigrationResult) -> None:
        if not result.v2_schema:
            return

        for resolved_choice in result.resolved_hardcoded_choices or []:
            field_schema = get_field_schema_from_prop_path(result.v2_schema, resolved_choice.property_path)
            rewrite_field_to_ref(field_schema, resolved_choice.resolution.choice_field_name)

    def migrate(self, migration_requests: List[str | dict]) -> List[MigrationResult]:
        """
        Main entry point for migrating EventTypes. Migrate multiple EventTypes.
        Atomic per EventType: each commits or rolls back independently.
        """
        results: list[MigrationResult] = []

        if not migration_requests:
            migration_requests = [
                MigrationRequest(event_type=et, event_type_value=et.value)
                for et in self.get_queryset().filter(version=EventType.VersionChoices.VERSION_1)
            ]
        else:
            # Normalize migration requests to MigrationRequest objects
            migration_requests = [MigrationRequest.from_input(item) for item in migration_requests]

        # Phase 1: Transform all v1 schemas to v2, gathering info about hardcoded choices
        for mr in migration_requests:
            result = self.build_migration_result(mr)
            results.append(result)

        # Phase 2: Analyze hardcoded choices and determine possible resolutions for all
        self.existing_choices = self.load_existing_choice_fields()
        self.proposed_choices = {}
        choice_processor = ChoiceProcessor()
        choice_processor.populate_resolution_options(results, self.existing_choices, self.proposed_choices)

        # Phase 3: Validate migration requests and prepare for persistence
        self.resolve_and_validate_migration_requests(results, choice_processor)
        for result in results:
            if result.success:
                try:
                    self.rewrite_resolved_choice_refs(result)
                except KeyError as e:
                    result.errors.append(f"Failed to rewrite resolved choice references: {str(e)}")

        if self.dry_run:
            return results

        # Phase 4: Persistence (only if not dry run)
        # We build a data structure that holds what choices have been successfully created
        # So we know how to handle the ones that may depend on them
        # Atomic persist for each event type schema and it's associated choices while respecting dependencies
        persisted_choice_fields: set[str] = set()

        for result in results:
            if not result.success:
                continue

            if not self.can_persist_result(result, persisted_choice_fields):
                continue

            with transaction.atomic():
                self.persist_migration(result, choice_processor)
                if not result.success:
                    transaction.set_rollback(True)
                    continue

            persisted_choice_fields.update(self.get_created_choice_field_names(result))

        return results

    def build_migration_result(self, migration_request: MigrationRequest) -> MigrationResult:
        """
        First pass: Get event type, get current schema, transform to V2, look for hardcoded choices.
        """
        et_value = migration_request.event_type_value
        result = MigrationResult(
            event_type_value=et_value,
            log=self.logger.for_event_type(et_value),
            event_type=migration_request.event_type,
            migration_request=migration_request,
        )
        event_type = result.event_type

        if not event_type:
            try:
                event_type = self.get_queryset().get(value=et_value)
                result.event_type = event_type
            except EventType.DoesNotExist:
                result.errors.append(
                    result.log.error(ErrorCode.EVENT_TYPE_NOT_FOUND, f"EventType '{et_value}' not found")
                )
                return result

        # Check authorization (skip for dry-run previews)
        if not self.dry_run and not self.can_modify_event_type(event_type):
            result.errors.append(
                result.log.error(ErrorCode.PERMISSION_DENIED, f"Permission denied for EventType '{et_value}'")
            )
            return result

        if event_type.version != EventType.VersionChoices.VERSION_1:
            result.errors.append(result.log.error(ErrorCode.VERSION_VALIDATION, f"EventType '{et_value}' is not V1"))
            return result

        # Transform schema
        self.populate_transformed_schema(result)
        if not result.success:
            return result

        result.hardcoded_choices = ChoiceProcessor().get_hardcoded_choices(result.v2_schema)
        return result

    def populate_transformed_schema(self, result: MigrationResult):
        """Transform V1 schema to V2 schema and collect transformation metadata.

        Args:
            result (MigrationResult): Migration result to update with transformed schema and metadata.
        """
        log_collector = LogCollector({"event_type": result.event_type.value})

        try:
            v1_schema = json.loads(preprocess_template_vars(result.event_type.schema))
        except json.JSONDecodeError as e:
            result.errors.append(result.log.error(ErrorCode.SCHEMA_PARSE, f"Invalid JSON in schema: {e}"))
            return

        transformed_schema = transform_schema(v1_schema, log_collector)

        # Collect warnings/errors from transformation
        for warning in log_collector.get_warnings():
            result.warnings.append(result.log.warning(ErrorCode.SCHEMA_TRANSFORM, warning.get("message")))
        for error in log_collector.get_errors():
            result.errors.append(result.log.error(ErrorCode.SCHEMA_TRANSFORM, error.get("message")))

        # Store transformation metadata
        features = log_collector.get_features()
        result.metadata["ignored_properties"] = features.get("ignoredProperties", [])
        result.metadata["unsupported_features"] = features.get("unsupportedFeatures", [])

        if len(result.metadata["unsupported_features"]) > 0:
            result.errors.append(
                result.log.error(
                    ErrorCode.UNSUPPORTED_FEATURES,
                    "Unsupported features found in schema: look at metadata for details",
                )
            )

        if result.errors:
            return

        result.v2_schema = transformed_schema

    def persist_migration(self, result: MigrationResult, choice_processor: ChoiceProcessor) -> None:
        if not result.success:
            return

        event_type = result.event_type

        try:
            for resolved_choice in result.resolved_hardcoded_choices or []:
                resolution = resolved_choice.resolution
                if resolution.strategy != ResolutionStrategy.CREATE_NEW:
                    continue
                choice_processor.create_choice_field(resolution.choice_field_name, resolved_choice.choices)

            for resolved_choice in result.resolved_hardcoded_choices or []:
                resolution = resolved_choice.resolution
                if resolution.strategy not in (
                    ResolutionStrategy.MERGE_INTO_EXISTING,
                    ResolutionStrategy.MERGE_INTO_PROPOSED,
                ):
                    continue
                choice_processor.add_values_to_choice_field(
                    resolution.choice_field_name,
                    resolution.missing_choices or [],
                )

            self.rewrite_resolved_choice_refs(result)

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
