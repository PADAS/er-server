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

from activity.models import EventType
from activity.permissions import EventCategoryPermissions

from .choice_processor import ChoiceProcessor

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of migrating a single EventType."""

    event_type: str
    v2_schema: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "v2_schema": self.v2_schema,
            "warnings": self.warnings,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class MigrationService:
    """
    Service for migrating V1 EventType schemas to V2.

    Usage:
        service = MigrationService(request=request)
        results = service.migrate(event_types=["snare_rep", "fence_rep"], dry_run=True)
    """

    def __init__(self, request, dry_run: bool = True):
        """
        Args:
            request: DRF request, required for authorization and URL context
            dry_run: If True, don't persist changes to database
        """
        self.request = request
        self.dry_run = dry_run

    def migrate(self, event_types: List[str]) -> List[MigrationResult]:
        """
        Migrate multiple EventTypes from V1 to V2.
        """
        results: list[MigrationResult] = []

        for event_type_value in event_types:
            result = self.migrate_single(event_type_value)
            results.append(result)

        return results

    def migrate_single(self, event_type_value: str) -> MigrationResult:
        """Migrate a single EventType."""
        # Shared context between phases
        result = MigrationResult(event_type=event_type_value)

        try:
            event_type = EventType.objects.get(value=event_type_value)
        except EventType.DoesNotExist:
            result.errors.append(f"EventType '{event_type_value}' not found")
            return result

        # Check authorization
        if not self.can_modify_event_type(event_type) and not self.dry_run:
            result.errors.append(f"Permission denied for EventType '{event_type_value}'")
            return result

        if event_type.version != EventType.VersionChoices.VERSION_1:
            result.errors.append(f"EventType '{event_type_value}' is not V1")
            return result

        # Transform schema
        v2_schema = self.transform_schema(event_type, result)
        if v2_schema is None:
            return result

        # Post-process
        v2_schema = self.process_choices(v2_schema, result)

        # Set result schema
        result.v2_schema = v2_schema

        # Persist if not dry_run
        if not self.dry_run and result.success:
            self.persist_choices(result)
            self.persist_migration(event_type, result)

        return result

    def transform_schema(self, event_type: EventType, result: MigrationResult) -> Optional[Dict[str, Any]]:
        """Transform V1 schema to V2 using schema_migration_tool."""
        log_collector = LogCollector(
            context={
                "event_type": event_type.value,
                "id": str(event_type.id),
            }
        )

        try:
            v2_schema = transform_schema(event_type.schema, log_collector)
        except Exception as e:
            logger.exception("Schema transformation failed for %s", event_type.value)
            result.errors.append(f"Transformation failed: {str(e)}")
            return None

        # Collect warnings/errors from transformation
        for warning in log_collector.get_warnings():
            result.warnings.append(warning.get("message", str(warning)))

        for error in log_collector.get_errors():
            result.errors.append(error.get("message", str(error)))

        # Store transformation metadata
        features = log_collector.get_features()
        result.metadata["field_types"] = features.get("fieldTypes", {})
        result.metadata["ignored_properties"] = features.get("ignoredProperties", [])
        result.metadata["choice_lists_detected"] = features.get("choiceLists", [])

        return v2_schema

    def process_choices(self, v2_schema: Dict[str, Any], result: MigrationResult) -> Dict[str, Any]:
        """Analyze hardcoded choices in the V2 schema (no DB writes)."""
        choice_processor = ChoiceProcessor(event_type_value=result.event_type)

        v2_schema, choice_metadata = choice_processor.process_hardcoded_choices(v2_schema)

        if choice_metadata:
            result.metadata["choices"] = choice_metadata
            for warning in choice_metadata.get("warnings", []):
                result.warnings.append(warning)

        return v2_schema

    def persist_choices(self, result: MigrationResult) -> None:
        """
        Persist choice fields to the database.

        Handles:
        - Creating new choice fields (status="to_create")
        - Adding missing values to existing fields (status="matched_with_additions")
        - Reusing choice fields within the same event type migration
        """
        choice_metadata = result.metadata.get("choices", {})
        fields = choice_metadata.get("fields", [])

        if not fields:
            return

        choice_processor = ChoiceProcessor(event_type_value=result.event_type)

        # Track choice fields created during this migration for reuse
        created_this_migration: Dict[str, str] = {}  # normalized_values_key -> field_name

        for field_info in fields:
            status = field_info.get("status")

            if status == "to_create":
                values = field_info.get("values", [])
                proposed_name = field_info.get("proposed_name")

                # Check if we already created a similar choice field in this migration
                values_key = self._get_values_key(values, choice_processor)
                if values_key in created_this_migration:
                    # Reuse the previously created choice field
                    reused_name = created_this_migration[values_key]
                    field_info["existing_choice_field"] = reused_name
                    field_info["status"] = "reused"
                    logger.info(
                        "Field '%s' reusing choice field '%s' created earlier in this migration",
                        field_info.get("field_name"),
                        reused_name,
                    )
                    continue

                # Create new choice field
                try:
                    choice_processor.create_choice_field(proposed_name, values)
                    field_info["existing_choice_field"] = proposed_name
                    field_info["status"] = "created"
                    created_this_migration[values_key] = proposed_name
                    logger.info(
                        "Created choice field '%s' for field '%s'",
                        proposed_name,
                        field_info.get("field_name"),
                    )
                except Exception as e:
                    field_info["status"] = "error"
                    field_info["error"] = str(e)
                    logger.exception(
                        "Failed to create choice field '%s'",
                        proposed_name,
                    )

            elif status == "matched_with_additions":
                values_to_add = field_info.get("values_to_add", [])
                existing_field = field_info.get("existing_choice_field")

                if values_to_add and existing_field:
                    try:
                        added = choice_processor.add_values_to_choice_field(existing_field, values_to_add)
                        field_info["values_added"] = added
                        logger.info(
                            "Added %d values to existing choice field '%s'",
                            added,
                            existing_field,
                        )
                    except Exception as e:
                        field_info["error"] = str(e)
                        logger.exception(
                            "Failed to add values to choice field '%s'",
                            existing_field,
                        )

    def _get_values_key(self, values: List[Dict[str, str]], processor: ChoiceProcessor) -> str:
        """Generate a key for a set of values for deduplication."""
        normalized = sorted(processor.normalize_for_matching(v.get("const", "")) for v in values)
        return "|".join(normalized)

    def persist_migration(self, event_type: EventType, result: MigrationResult) -> None:
        """Persist the migrated schema to the database."""
        event_type.schema = json.dumps(result.v2_schema, indent=2)
        event_type.version = EventType.VersionChoices.VERSION_2
        event_type.save(update_fields=["schema", "version", "updated_at"])
        result.metadata["persisted"] = True
        logger.info("Successfully migrated EventType '%s' to V2", event_type.value)

    def can_modify_event_type(self, event_type: EventType) -> bool:
        """
        Check if the current user can modify the given EventType.
        """
        # Simulate a PATCH request for update permission check
        original_method = self.request.method
        try:
            self.request.method = "PATCH"
            permission = EventCategoryPermissions()
            return permission.has_object_permission(self.request, view=None, obj=event_type)
        finally:
            self.request.method = original_method
