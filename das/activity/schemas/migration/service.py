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
from django.urls import reverse

from activity.models import EventType
from activity.permissions import EventCategoryPermissions
from choices.models import Choice

from .choice_processor import ChoiceProcessor

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of migrating a single EventType."""

    event_type: str
    event_type_instance: Optional["EventType"] = field(default=None, repr=False)
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
    """Orchestrates V1 → V2 EventType schema migration.

    Two-phase: analyze all event types first, then persist atomically.
    """

    def __init__(self, request, dry_run: bool = True):
        self.request = request
        self.dry_run = dry_run
        self.choices_base_url = reverse("schemas:choices")
        self.existing_choices: Dict[str, List[str]] = {}
        self.proposed_choices: Dict[str, List[str]] = {}

    def migrate(self, event_types: List[str]) -> List[MigrationResult]:
        """Migrate multiple EventTypes. Atomic per EventType: each commits or rolls back independently."""
        self.proposed_choices: Dict[str, list] = {}
        self.existing_choices: Dict[str, List[str]] = self.get_existing_choice_fields()

        results: list[MigrationResult] = []

        # Phase 1: Analyze all event types (no DB writes)
        for event_type_value in event_types:
            result = self.migrate_single(event_type_value)
            results.append(result)

        # Phase 2: Persistence (atomic per EventType)
        if not self.dry_run:
            for result in results:
                with transaction.atomic():
                    self.persist_choices(result)
                    if not result.success:
                        transaction.set_rollback(True)
                    self.persist_migration(result.event_type_instance, result)
                    if not result.success:
                        transaction.set_rollback(True)

        return results

    def migrate_single(self, event_type_value: str) -> MigrationResult:
        """Analyze a single EventType for migration (no persistence)."""
        result = MigrationResult(event_type=event_type_value)

        try:
            event_type = EventType.objects.get(value=event_type_value)
        except EventType.DoesNotExist:
            result.errors.append(f"EventType '{event_type_value}' not found")
            return result

        result.event_type_instance = event_type

        # Check authorization
        if not self.can_modify_event_type(event_type) and not self.dry_run:
            result.errors.append(f"Permission denied for EventType '{event_type_value}'")
            return result

        if event_type.version != EventType.VersionChoices.VERSION_1:
            result.errors.append(f"EventType '{event_type_value}' is not V1")
            return result

        # Transform schema
        v2_schema = self.transform_schema(event_type, result)
        if v2_schema is None or not result.success:
            return result

        # Post-process schema (add hard-coded choices)
        v2_schema = self.process_choices(v2_schema, result)

        # Set result schema, only after all schema processing is done, including hard-coded choices
        result.v2_schema = v2_schema

        return result

    def transform_schema(self, event_type: EventType, result: MigrationResult) -> Optional[dict]:
        log_collector = LogCollector({"event_type": event_type.value})

        try:
            v1_schema = json.loads(preprocess_template_vars(event_type.schema))
        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON in schema: {e}")
            return None

        v2_schema = transform_schema(v1_schema, log_collector)

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

        return v2_schema

    def process_choices(self, v2_schema: dict, result: MigrationResult) -> dict:
        """Delegate to ChoiceProcessor; block migration if any candidate fields found."""
        choice_processor = ChoiceProcessor(
            event_type_value=result.event_type,
            choices_base_url=self.choices_base_url,
            proposed_choices=self.proposed_choices,
            existing_choices=self.existing_choices,
        )

        v2_schema, choice_metadata = choice_processor.process_hardcoded_choices(v2_schema)

        if choice_metadata:
            result.metadata["choices"] = choice_metadata
            for warning in choice_metadata.get("warnings", []):
                result.warnings.append(warning)

            # Block migration if any candidate (partial match) fields found
            candidate_fields = [f for f in choice_metadata.get("fields", []) if f.get("status") == "candidate"]
            for field_info in candidate_fields:
                result.errors.append(
                    f"Field '{field_info['field_name']}' has a partial match with "
                    f"existing choice list '{field_info['existing_choice_field']}'. "
                    f"Cannot auto-migrate - manual resolution required."
                )

        return v2_schema

    def persist_choices(self, result: MigrationResult) -> None:
        """Create Choice objects for 'to_create' fields. Deduplicates by
        normalized values so identical choice sets share one DB field.
        """
        choice_metadata = result.metadata.get("choices", {})
        fields = choice_metadata.get("fields", [])

        if not fields:
            return

        choice_processor = ChoiceProcessor(
            event_type_value=result.event_type,
            choices_base_url=self.choices_base_url,
            proposed_choices=self.proposed_choices,
            existing_choices=self.existing_choices,
        )

        # Track choice fields created during this migration for reuse
        created_this_migration: Dict[str, str] = {}  # normalized_values_key -> field_name

        for field_info in fields:
            status = field_info.get("status")

            if status == "to_create":
                choices = field_info.get("choices", [])
                proposed_name = field_info.get("proposed_name")

                # Check if we already created a similar choice field in this migration
                values_key = self._get_values_key(choices, choice_processor)
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
                    choice_processor.create_choice_field(proposed_name, choices)
                    field_info["existing_choice_field"] = proposed_name
                    field_info["status"] = "created"
                    created_this_migration[values_key] = proposed_name
                    logger.info(
                        "Created choice field '%s' with %d values for event type '%s'",
                        proposed_name,
                        len(choices),
                        result.event_type,
                    )
                except Exception as e:
                    field_info["status"] = "error"
                    field_info["error"] = str(e)
                    result.errors.append(f"Failed to create choice field '{proposed_name}': {e}")
                    logger.exception(
                        "Failed to create choice field '%s'",
                        proposed_name,
                    )

    def _get_values_key(self, choices: List[Dict[str, str]], processor: ChoiceProcessor) -> str:
        normalized = sorted(processor.normalize_for_matching(v.get("value", "")) for v in choices)
        return "|".join(normalized)

    def persist_migration(self, event_type: EventType, result: MigrationResult) -> None:
        event_type.schema = json.dumps(result.v2_schema, indent=2)
        event_type.version = EventType.VersionChoices.VERSION_2
        event_type.save(update_fields=["schema", "version", "updated_at"])
        result.metadata["persisted"] = True
        logger.info("Successfully migrated EventType '%s' to V2", event_type.value)

    def can_modify_event_type(self, event_type: EventType) -> bool:
        # Simulate PATCH to reuse DRF object-level permission check
        original_method = self.request.method
        try:
            self.request.method = "PATCH"
            permission = EventCategoryPermissions()
            return permission.has_object_permission(self.request, view=None, obj=event_type)
        finally:
            self.request.method = original_method

    def get_existing_choice_fields(self) -> Dict[str, List[str]]:
        """Load active Event choice fields from DB as {field_name: [values]}."""

        choices = Choice.objects.filter(model=Choice.EVENT_MODEL, is_active=True).values_list("field", "value")

        fields: Dict[str, List[str]] = {}
        for field_name, value in choices:
            if field_name not in fields:
                fields[field_name] = []
            fields[field_name].append(value)

        return fields
