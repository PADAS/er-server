"""
Migration service that orchestrates V1 to V2 schema transformation.

This is the main entry point for migration operations, coordinating:
- Schema transformation via schema_migration_tool
- Post-processing (choice conversion, URL updates)
- Result collection with warnings/errors
"""

from __future__ import annotations

import json
import logging
from copy import copy
from dataclasses import dataclass, field
from typing import Any

from schema_migration_tool import LogCollector, transform_schema
from schema_migration_tool.batch.normalize_export import preprocess_template_vars

from django.db import transaction
from django.db.models import QuerySet

from activity.models import EventType
from activity.permissions import EventCategoryPermissions
from activity.schemas.utils import get_field_schema_from_prop_path
from choices.models import Choice

from .choice_processor import (
    ChoiceProcessor,
    HardcodedChoice,
    HardcodedChoiceResolution,
    ResolutionStrategy,
)
from .logger import ErrorCode, EventTypeMigrationLogger, MigrationLogger
from .utils import rewrite_field_to_ref

logger = logging.getLogger(__name__)


@dataclass
class MigrationRequest:
    event_type_value: str
    event_type: EventType | None = None
    hardcoded_choices_resolutions: list[HardcodedChoiceResolution] | None = None

    @classmethod
    def _normalize_resolution(cls, data: HardcodedChoiceResolution | dict) -> HardcodedChoiceResolution:
        if isinstance(data, HardcodedChoiceResolution):
            return data
        return HardcodedChoiceResolution.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> MigrationRequest:
        normalized_data = data.copy()

        if "hardcoded_choices_resolutions" in normalized_data and normalized_data["hardcoded_choices_resolutions"]:
            normalized_data["hardcoded_choices_resolutions"] = [
                cls._normalize_resolution(item) for item in normalized_data["hardcoded_choices_resolutions"]
            ]

        return cls(**normalized_data)

    @classmethod
    def from_input(cls, data: MigrationRequest | str | dict[str, Any]) -> MigrationRequest:
        if isinstance(data, cls):
            return data

        if isinstance(data, str):
            return cls(event_type_value=data)

        if isinstance(data, dict):
            return cls.from_dict(data)

        raise TypeError("MigrationRequest input must be a MigrationRequest, str, or dict")


@dataclass
class ResolvedHardcodedChoice:
    property_path: list[str]
    choices: list[dict[str, str]]
    resolution: HardcodedChoiceResolution


@dataclass
class MigrationResult:
    """Result of migrating a single EventType."""

    log: EventTypeMigrationLogger
    event_type_value: str = ""
    event_type: EventType | None = None
    migration_request: MigrationRequest | None = None
    v2_schema: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    hardcoded_choices: list[HardcodedChoice] | None = None
    resolved_hardcoded_choices: list[ResolvedHardcodedChoice] | None = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class MigrationService:
    """Orchestrates V1 → V2 EventType schema migration.

    Two-phase: analyze all event types first, then persist atomically.
    """

    def __init__(
        self,
        *,
        request,
        dry_run: bool = True,
        queryset: QuerySet | None = None,
        logger: MigrationLogger | None = None,
    ):
        self.request = request
        self._queryset = queryset
        self.dry_run = dry_run
        self.existing_choices: dict[str, list[str]] = {}
        self.proposed_choices: dict[str, list[str]] = {}
        self.logger: MigrationLogger = logger or MigrationLogger.from_request(request, dry_run=dry_run)

    def get_queryset(self) -> QuerySet[EventType]:
        if self._queryset is not None:
            return self._queryset

        self._queryset = EventType.objects.filter(
            category__is_active=True,  # Always filter out inactive categories.
        ).select_related("category")

        return self._queryset

    def load_existing_choice_fields(self) -> dict[str, list[str]]:
        """
        Get existing choice fields from the database.
        """
        fields: dict[str, list[str]] = {}
        choices = Choice.objects.filter(model=Choice.EVENT_MODEL, is_active=True).values_list("field", "value")

        for field_name, value in choices:
            if field_name not in fields:
                fields[field_name] = []
            fields[field_name].append(value)

        return fields

    def index_selected_resolutions(self, result: MigrationResult) -> dict[tuple[str, ...], HardcodedChoiceResolution]:
        """
        Index selected resolutions by property path (as tuple) for quick lookup.
        """
        selected_resolutions: dict[tuple[str, ...], HardcodedChoiceResolution] = {}

        if not result.migration_request or not result.migration_request.hardcoded_choices_resolutions:
            return selected_resolutions

        for resolution in result.migration_request.hardcoded_choices_resolutions:

            property_path = tuple(resolution.property_path)
            if property_path in selected_resolutions:
                result.errors.append(
                    result.log.error(
                        ErrorCode.DUPLICATE_RESOLUTION,
                        f"Duplicate hardcoded choice resolution for property path: {resolution.property_path}",
                    )
                )
                continue

            selected_resolutions[property_path] = resolution

        return selected_resolutions

    def validate_selected_resolutions(
        self,
        result: MigrationResult,
        selected_resolutions: dict[tuple[str, ...], HardcodedChoiceResolution],
        hardcoded_choices_by_path: dict[tuple[str, ...], HardcodedChoice],
        choice_processor: ChoiceProcessor,
    ) -> None:
        for property_path, resolution in selected_resolutions.items():
            hardcoded_choice = hardcoded_choices_by_path.get(property_path)
            if hardcoded_choice is None:
                result.errors.append(
                    result.log.error(
                        ErrorCode.UNKNOWN_RESOLUTION_PATH,
                        f"Unknown hardcoded choice resolution property path: {resolution.property_path}",
                    )
                )
                continue

            if choice_processor.find_matching_resolution_option(hardcoded_choice, resolution) is None:
                result.errors.append(
                    result.log.error(
                        ErrorCode.INVALID_RESOLUTION,
                        f"Invalid resolution for property path {resolution.property_path}: "
                        f"{resolution.strategy} -> {resolution.choice_field_name}",
                    )
                )

    def get_effective_resolution(
        self,
        hardcoded_choice: HardcodedChoice,
        selected_resolutions: dict[tuple[str, ...], HardcodedChoiceResolution],
        choice_processor: ChoiceProcessor,
    ) -> HardcodedChoiceResolution | None:
        property_path = tuple(hardcoded_choice.property_path)
        selected_resolution = selected_resolutions.get(property_path)

        if selected_resolution is None:
            option = hardcoded_choice.resolution_options[0]
            return HardcodedChoiceResolution(
                strategy=option.strategy,
                choice_field_name=option.choice_field_name,
                property_path=list(option.property_path or hardcoded_choice.property_path),
            )

        matched_option = choice_processor.find_matching_resolution_option(hardcoded_choice, selected_resolution)
        if matched_option is None:
            return None

        return HardcodedChoiceResolution(
            strategy=selected_resolution.strategy,
            choice_field_name=selected_resolution.choice_field_name or matched_option.choice_field_name,
            property_path=list(selected_resolution.property_path or matched_option.property_path or property_path),
        )

    def build_resolved_hardcoded_choices(
        self,
        result: MigrationResult,
        selected_resolutions: dict[tuple[str, ...], HardcodedChoiceResolution],
        choice_processor: ChoiceProcessor,
    ) -> list[ResolvedHardcodedChoice]:
        resolved_hardcoded_choices: list[ResolvedHardcodedChoice] = []

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
        results: list[MigrationResult],
    ) -> dict[str, int]:
        create_new_targets: dict[str, int] = {}

        for result_index, result in enumerate(results):
            if not result.success or not result.resolved_hardcoded_choices:
                continue

            for resolved_choice in result.resolved_hardcoded_choices:
                resolution = resolved_choice.resolution
                if resolution.strategy != ResolutionStrategy.CREATE_NEW:
                    continue

                choice_field_name = resolution.choice_field_name

                if choice_field_name in self.existing_choices:
                    result.errors.append(
                        result.log.error(
                            ErrorCode.CHOICE_FIELD_EXISTS,
                            f"Choice field '{choice_field_name}' already exists and cannot be created again",
                        )
                    )
                    continue

                if choice_field_name in create_new_targets:
                    result.errors.append(
                        result.log.error(
                            ErrorCode.CHOICE_FIELD_BATCH_CONFLICT,
                            f"Choice field '{choice_field_name}' is already planned for creation in this batch",
                        )
                    )
                    continue

                create_new_targets[choice_field_name] = result_index

        return create_new_targets

    def validate_resolution_dependencies(
        self,
        results: list[MigrationResult],
        create_new_targets: dict[str, int],
    ) -> None:
        for result_index, result in enumerate(results):
            if not result.success or not result.resolved_hardcoded_choices:
                continue

            for resolved_choice in result.resolved_hardcoded_choices:
                resolution = resolved_choice.resolution
                choice_field_name = resolution.choice_field_name

                if resolution.strategy != ResolutionStrategy.USE_PROPOSED:
                    continue

                producer_index = create_new_targets.get(choice_field_name)
                if producer_index is None:
                    result.errors.append(
                        result.log.error(
                            ErrorCode.DEPENDENCY_NOT_FOUND,
                            f"Proposed choice field '{choice_field_name}' is not planned for creation in this batch",
                        )
                    )
                    continue

                if producer_index > result_index:
                    result.errors.append(
                        result.log.error(
                            ErrorCode.DEPENDENCY_ORDER,
                            f"Proposed choice field '{choice_field_name}' is created by a later migration request",
                        )
                    )
                    continue

                producer_result = results[producer_index]
                if not producer_result.success:
                    result.errors.append(
                        result.log.error(
                            ErrorCode.DEPENDENCY_INVALID,
                            f"Proposed choice field '{choice_field_name}' depends on an invalid migration request",
                        )
                    )

    def resolve_and_validate_migration_requests(
        self,
        results: list[MigrationResult],
        choice_processor: ChoiceProcessor,
    ) -> None:
        selected_resolutions_by_result: dict[int, dict[tuple[str, ...], HardcodedChoiceResolution]] = {}

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
                if resolved_choice.resolution.strategy == ResolutionStrategy.USE_PROPOSED
                and resolved_choice.resolution.choice_field_name not in local_created_fields
                and resolved_choice.resolution.choice_field_name not in persisted_choice_fields
            }
        )

        if not blocked_fields:
            return True

        result.errors.append(
            result.log.error(
                ErrorCode.DEPENDENCY_NOT_PERSISTED,
                f"Proposed choice field dependencies were not persisted successfully: {', '.join(blocked_fields)}",
            )
        )
        return False

    def rewrite_resolved_choice_refs(self, result: MigrationResult) -> None:
        if not result.v2_schema:
            return

        for resolved_choice in result.resolved_hardcoded_choices or []:
            field_schema = get_field_schema_from_prop_path(result.v2_schema, resolved_choice.property_path)
            if field_schema is None:
                raise KeyError(f"Property path not found in v2 schema: {resolved_choice.property_path}")
            rewrite_field_to_ref(field_schema, resolved_choice.resolution.choice_field_name)

    def migrate(self, migration_requests: list[str | dict]) -> list[MigrationResult]:
        """
        Main entry point for migrating EventTypes. Migrate multiple EventTypes.
        Atomic per EventType: each commits or rolls back independently.
        """
        results: list[MigrationResult] = []
        _migration_requests: list[MigrationRequest] = []

        if not migration_requests:
            _migration_requests = [
                MigrationRequest(event_type=et, event_type_value=et.value)
                for et in self.get_queryset().filter(version=EventType.VersionChoices.VERSION_1)
            ]
        else:
            # Normalize migration requests to MigrationRequest objects
            _migration_requests = [MigrationRequest.from_input(item) for item in migration_requests]

        # Phase 1: Transform all v1 schemas to v2, gathering info about hardcoded choices
        for mr in _migration_requests:
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
                except (KeyError, TypeError) as e:
                    # Known case: Property path not found in v2 schema
                    result.errors.append(
                        result.log.error(
                            ErrorCode.REPLACE_REF_FAILED,
                            f"Failed to replace resolved choice reference: {str(e)}",
                        )
                    )

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
        if not result.success or not result.event_type:
            return

        event_type = result.event_type

        try:
            for resolved_choice in result.resolved_hardcoded_choices or []:
                resolution = resolved_choice.resolution
                if resolution.strategy != ResolutionStrategy.CREATE_NEW:
                    continue
                choice_processor.create_choice_field(resolution.choice_field_name, resolved_choice.choices)

            event_type.schema = json.dumps(result.v2_schema, indent=2)
            event_type.version = EventType.VersionChoices.VERSION_2
            event_type.save(update_fields=["schema", "version", "updated_at"])
        except Exception as e:
            result.errors.append(result.log.error(ErrorCode.PERSIST_FAILED, f"Failed to persist migration: {e}"))
            return

        result.metadata["persisted"] = True

    def can_modify_event_type(self, event_type: EventType) -> bool:
        # Simulate PATCH to reuse DRF object-level permission check.
        # Use a shallow copy to avoid mutating the live request (thread-safety).
        request_copy = copy(self.request)
        request_copy.method = "PATCH"
        permission = EventCategoryPermissions()
        return permission.has_object_permission(request_copy, view=None, obj=event_type)
