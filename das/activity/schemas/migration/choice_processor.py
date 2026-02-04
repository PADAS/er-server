"""
Hardcoded choice processing for migrated V2 schemas.

This module handles:
- Extracting hardcoded values from anyOf/oneOf structures in V2 schemas
- Finding matching Choice objects in the database
- Generating unique names for new choice fields
- Creating new Choice objects when needed (respects dry_run)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from django.db import models

from choices.models import Choice

logger = logging.getLogger(__name__)


@dataclass
class ChoiceFieldResult:
    """Result for a single choice field processing."""

    field_name: str
    status: str = "pending"  # "matched", "candidate", "to_create", "error"
    existing_choice_field: Optional[str] = None
    proposed_name: Optional[str] = None
    values: List[Dict[str, str]] = field(default_factory=list)  # [{const, title}, ...]
    values_to_add: List[Dict[str, str]] = field(default_factory=list)  # values missing from existing field
    match_score: float = 0.0  # 0-1, how well values match existing
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "status": self.status,
            "existing_choice_field": self.existing_choice_field,
            "proposed_name": self.proposed_name,
            "values": self.values,
            "values_to_add": self.values_to_add,
            "match_score": self.match_score,
            "warnings": self.warnings,
            "error": self.error,
        }


class ChoiceProcessor:
    """
    Processes hardcoded choices in migrated V2 schemas.

    Detects inline choice values and matches them against existing Choice
    objects in the database, or flags them for creation.
    """

    # Minimum overlap ratio to consider an existing choice field a "match"
    MATCH_THRESHOLD = 2 / 3

    # Separator normalization pattern for matching
    SEPARATOR_PATTERN = re.compile(r"[-_.\s]+")

    def __init__(self, event_type_value: Optional[str] = None):
        """
        Args:
            event_type_value: The event type value, used for generating unique names
        """
        self.event_type_value = event_type_value

    def process_hardcoded_choices(self, v2_schema: Dict[str, Any]) -> Tuple[dict]:
        """
        Process hardcoded choices in a V2 schema.

        Args:
            v2_schema: The migrated V2 schema

        Returns:
            Tuple of (modified_schema, metadata)
            - modified_schema: Schema with choices potentially rewritten to $ref
            - metadata: Dict with results per field, warnings, summary
        """
        metadata = {
            "fields": [],
            "warnings": [],
            "summary": {
                "matched": 0,
                "candidate": 0,
                "to_create": 0,
                "created": 0,
                "errors": 0,
            },
        }

        json_schema = v2_schema.get("json", {})
        properties = json_schema.get("properties", {})

        for field_name, field_schema in properties.items():
            # Check if this field has hardcoded choices (anyOf with oneOf inside)
            hardcoded_values = self.extract_hardcoded_values(field_schema)

            if not hardcoded_values:
                continue

            result = self.process_single_field(
                field_name=field_name,
                field_schema=field_schema,
                hardcoded_values=hardcoded_values,
            )

            metadata["fields"].append(result.to_dict())

            # Update summary
            if result.status == "matched":
                metadata["summary"]["matched"] += 1
            elif result.status == "candidate":
                metadata["summary"]["candidate"] += 1
            elif result.status == "to_create":
                metadata["summary"]["to_create"] += 1
            elif result.status == "created":
                metadata["summary"]["created"] += 1
            elif result.status == "error":
                metadata["summary"]["errors"] += 1

            # Collect warnings
            metadata["warnings"].extend(result.warnings)

        return v2_schema, metadata

    def extract_hardcoded_values(self, field_schema: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract hardcoded choice values from a V2 field schema.

        V2 hardcoded format:
        {
            "anyOf": [{
                "title": "Hardcoded",
                "type": "string",
                "oneOf": [
                    {"const": "value1", "title": "Display 1"},
                    {"const": "value2", "title": "Display 2"}
                ]
            }]
        }

        Returns:
            List of {value, display} dicts, or empty list if not hardcoded
        """
        any_of = field_schema.get("anyOf", [])
        if not any_of:
            return []

        for option in any_of:
            # Skip $ref entries (already pointing to existing choice list)
            if "$ref" in option:
                return []

            # Look for hardcoded oneOf structure
            one_of = option.get("oneOf", [])
            if one_of and option.get("title") == "Hardcoded":
                values = [{"value": item["const"], "display": item.get("title", item["const"])} for item in one_of]
                return values

        return []

    def process_single_field(
        self, field_name: str, field_schema: Dict[str, Any], hardcoded_values: List[Dict[str, str]]
    ) -> ChoiceFieldResult:
        """
        Analyze a single field with hardcoded choices.

        This method only analyzes and proposes actions - no DB writes.
        The service's persist_choices() handles actual persistence.
        """
        result = ChoiceFieldResult(field_name=field_name, values=hardcoded_values)

        # 1. Try to find matching existing choice field
        match = self.find_matching_choice_field(field_name, hardcoded_values)

        if match:
            existing_field_name, score, missing_values = match
            result.existing_choice_field = existing_field_name
            result.match_score = score
            result.values_to_add = missing_values

            if score == 1.0:
                result.status = "matched"
                logger.info(
                    "Field '%s' matched existing choice field '%s' (score: %.0f%%)",
                    field_name,
                    existing_field_name,
                    score * 100,
                )
            else:
                result.status = "candidate"
                logger.info(
                    "Field '%s' matched '%s' (%.0f%%), %d values to add",
                    field_name,
                    existing_field_name,
                    score * 100,
                    len(missing_values),
                )
            return result

        # 2. No match found - propose new choice field name
        proposed_name = self.generate_unique_name(field_name, field_schema)
        result.proposed_name = proposed_name
        result.status = "to_create"
        logger.info(
            "Field '%s' will create new choice field '%s'",
            field_name,
            proposed_name,
        )

        return result

    def normalize_for_matching(self, value: str) -> str:
        """
        Normalize a string for comparison during matching.

        - Lowercase
        - Replace separators (dash, underscore, dot, space) with a single dash
        - Strip leading/trailing separators
        """
        normalized = value.lower()
        normalized = self.SEPARATOR_PATTERN.sub("-", normalized)
        return normalized.strip("-")

    def slugify_for_choice(self, value: str) -> str:
        """
        Convert a string to a valid choice field name.

        - Lowercase
        - Replace non-alphanumeric characters with underscores
        - Strip leading/trailing underscores
        - Collapse multiple underscores
        """
        slugified = value.lower()
        slugified = re.sub(r"[^a-z0-9]+", "_", slugified)
        slugified = re.sub(r"_+", "_", slugified)
        return slugified.strip("_")

    def find_matching_choice_field(
        self, field_name: str, hardcoded_items: List[Dict[str, str]]
    ) -> Optional[Tuple[str, float, List[Dict[str, str]]]]:
        """
        Find an existing choice field that matches the hardcoded values.

        Uses normalized comparison (case-insensitive, separator-agnostic).

        Matching strategies:
        1. Exact name match with high value overlap
        2. Any field with high value overlap

        Returns:
            Tuple of (field_name, match_score, missing_values) or None if no match
            - missing_values: hardcoded values not found in existing field
        """
        # Build normalized -> original mapping for hardcoded values
        hardcoded_by_normalized = {self.normalize_for_matching(v["value"]): v for v in hardcoded_items}
        hardcoded_normalized = set(hardcoded_by_normalized.keys())
        hardcoded_values = [v["value"] for v in hardcoded_items]

        # Get all existing choice fields for events
        existing_fields = self.get_existing_choice_fields()

        best_match: Optional[Tuple[str, float, List[Dict[str, str]]]] = None

        for existing_field_name, existing_values in existing_fields.items():
            # Normalize existing values for comparison
            existing_normalized = {self.normalize_for_matching(v) for v in existing_values}

            if not existing_normalized:
                continue

            # Calculate overlap score (Jaccard similarity)
            # using normalized values
            intersection = hardcoded_normalized & existing_normalized
            union = hardcoded_normalized | existing_normalized
            normalized_score = len(intersection) / len(union) if union else 0.0
            # using original values
            intersection = set(hardcoded_values) & set(existing_values)
            union = set(hardcoded_values) | set(existing_values)
            value_score = len(intersection) / len(union) if union else 0.0

            # Early exit if exact match
            if value_score == 1.0:
                best_match = (existing_field_name, value_score, [])
                break

            # Prefer exact name match (also normalized)
            if self.normalize_for_matching(existing_field_name) == self.normalize_for_matching(field_name):
                value_score += 0.1  # Slight boost for name match
                value_score = min(value_score, 1.0)

            if normalized_score >= self.MATCH_THRESHOLD:
                # Find missing values (in hardcoded but not in existing)
                missing_normalized = hardcoded_normalized - existing_normalized
                missing_values = [hardcoded_by_normalized[n] for n in missing_normalized]

                if best_match is None or value_score > best_match[1]:
                    best_match = (existing_field_name, value_score, missing_values)

        return best_match

    def get_existing_choice_fields(self) -> Dict[str, List[str]]:
        """
        Get all existing choice fields and their values for the Event model.

        Returns:
            Dict mapping field_name -> list of values
        """
        choices = Choice.objects.filter(model=Choice.EVENT_MODEL, is_active=True).values_list("field", "value")

        fields: Dict[str, List[str]] = {}
        for field_name, value in choices:
            if field_name not in fields:
                fields[field_name] = []
            fields[field_name].append(value)

        return fields

    def generate_unique_name(self, field_name: str, field_schema: Dict[str, Any]) -> str:
        """
        Generate a unique name for a new choice field.

        Name generation strategy:
        1. Try field_name directly
        2. Try field title (slugified)
        3. Try event_type_value + field_name
        4. Add numeric suffix if needed

        Returns:
            A unique choice field name (alphanumeric + underscore only)
        """
        candidates = []

        # Candidate 1: field name directly
        candidates.append(self.slugify_for_choice(field_name))

        # Candidate 2: field title
        title = field_schema.get("title", "")
        if title:
            candidates.append(self.slugify_for_choice(title))

        # Candidate 3: event_type + field_name
        if self.event_type_value:
            candidates.append(self.slugify_for_choice(f"{self.event_type_value}_{field_name}"))

        # Get existing field names
        existing_names = set(self.get_existing_choice_fields().keys())

        # Try each candidate
        for candidate in candidates:
            if candidate not in existing_names:
                return candidate

        # All candidates taken - add numeric suffix
        base_name = candidates[0] if candidates else "choice"
        counter = 1
        while True:
            name = f"{base_name}_{counter}"
            if name not in existing_names:
                return name
            counter += 1

    def create_choice_field(self, field_name: str, values: List[Dict[str, str]]) -> None:
        """
        Create Choice objects for a new choice field.

        Args:
            field_name: The choice field name
            values: List of {value, display} dicts from extract_hardcoded_values
        """
        for i, item in enumerate(values):
            value = item["value"]
            if not value:
                logger.warning("Skipping empty value in choice field '%s'", field_name)
                continue

            Choice.objects.create(
                model=Choice.EVENT_MODEL,
                field=field_name,
                value=value,
                display=item.get("display", value),
                ordernum=i,
            )

    def add_values_to_choice_field(self, field_name: str, values: List[Dict[str, str]]) -> int:
        """
        Add missing values to an existing choice field.

        Args:
            field_name: The existing choice field name
            values: List of {value, display} dicts from extract_hardcoded_values

        Returns:
            Number of values actually added
        """
        # Get next ordernum for this field
        max_order = Choice.objects.filter(
            model=Choice.EVENT_MODEL,
            field=field_name,
        ).aggregate(
            max_order=models.Max("ordernum")
        )["max_order"]
        next_order = (max_order or 0) + 1

        added = 0
        for item in values:
            value = item["value"]
            if not value:
                continue

            # Check if value already exists (shouldn't, but be safe)
            if Choice.objects.filter(model=Choice.EVENT_MODEL, field=field_name, value=value).exists():
                continue

            Choice.objects.create(
                model=Choice.EVENT_MODEL,
                field=field_name,
                value=value,
                display=item.get("display", value),
                ordernum=next_order,
            )
            next_order += 1
            added += 1

        return added
