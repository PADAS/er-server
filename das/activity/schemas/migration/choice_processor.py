"""Hardcoded choice processing for migrated V2 schemas."""

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
    choices: List[Dict[str, str]] = field(default_factory=list)  # [{"value", "display"}, ...]
    choices_to_add: List[Dict[str, str]] = field(default_factory=list)  # choices missing from existing field
    match_score: float = 0.0  # 0-1, how well choices match existing
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "status": self.status,
            "existing_choice_field": self.existing_choice_field,
            "proposed_name": self.proposed_name,
            "choices": self.choices,
            "choices_to_add": self.choices_to_add,
            "match_score": self.match_score,
            "warnings": self.warnings,
            "error": self.error,
        }


class ChoiceProcessor:
    """Detects inline choice values in V2 schemas and matches them against
    existing Choice objects and proposed choices from the current batch.

    Statuses: matched (100%), candidate (partial, blocks migration), to_create (new).
    """

    # Minimum overlap ratio to consider an existing (or proposed) choice field a "match"
    MATCH_THRESHOLD = 2 / 3

    # Separator normalization pattern for matching
    SEPARATOR_PATTERN = re.compile(r"[-_.\s]+")

    def __init__(
        self,
        event_type_value: str,
        choices_base_url: str,
        proposed_choices: Optional[dict] = None,
        existing_choices: Optional[dict] = None,
    ):
        """
        Args:
            event_type_value: Used for generating unique choice field names.
            choices_base_url: Base URL for $ref rewriting.
            proposed_choices: Shared mutable registry across the migration batch.
                When a field is 'to_create', its values are added here so
                subsequent event types can match against them.
            existing_choices: Pre-loaded map of field_name -> [values] from DB.
        """
        self.event_type_value = event_type_value
        self.choices_base_url = choices_base_url
        self.proposed_choices = proposed_choices or {}
        self.existing_choices = existing_choices or {}

    def process_hardcoded_choices(self, v2_schema: Dict[str, Any]) -> Tuple[dict, dict]:
        """Analyze all fields, then rewrite ready ones to $ref.

        Two-phase approach: analyze all fields first so that the presence of
        any 'candidate' field blocks $ref rewriting for the entire schema.

        Returns (modified_schema, metadata).
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

        # Track proposed names within this batch to prevent collisions
        reserved_names = set(self.proposed_choices.keys())

        # Phase 1: Analyze all fields (no schema mutation)
        analyzed_fields = []  # list of (field_name, field_schema, result)

        for field_name, field_schema in properties.items():
            hardcoded_choices, dedupe_warnings = self.extract_hardcoded_choices(field_schema)

            if not hardcoded_choices:
                continue

            result = self.process_choices_single_field(
                field_name=field_name,
                field_schema=field_schema,
                hardcoded_choices=hardcoded_choices,
                reserved_names=reserved_names,
            )

            if dedupe_warnings:
                result.warnings.extend(dedupe_warnings)

            # Track proposed names to avoid collisions within batch
            if result.status == "to_create" and result.proposed_name:
                reserved_names.add(result.proposed_name)
                # Add to shared registry so subsequent fields can match
                if self.proposed_choices is not None:
                    self.proposed_choices[result.proposed_name] = [v["value"] for v in hardcoded_choices]

            analyzed_fields.append((field_name, field_schema, result))

        # Phase 2: Rewrite schemas and collect metadata
        # Only rewrite to $ref if no candidates were found in this schema
        has_candidates = any(r.status == "candidate" for _, _, r in analyzed_fields)

        for field_name, field_schema, result in analyzed_fields:
            if not has_candidates and self.choices_base_url and result.status in ("matched", "to_create"):
                ref_name = result.existing_choice_field if result.status == "matched" else result.proposed_name
                self.rewrite_field_to_ref(field_schema, ref_name)
            elif result.status == "candidate":
                result.warnings.append(
                    f"Field '{field_name}' has a partial match with '{result.existing_choice_field}' "
                    f"(score: {result.match_score:.0%}). Manual review required."
                )

            metadata["fields"].append(result.to_dict())
            self._update_summary(metadata["summary"], result.status)
            metadata["warnings"].extend(result.warnings)

        return v2_schema, metadata

    def extract_hardcoded_choices(self, field_schema: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[str]]:
        """Extract hardcoded choices from anyOf > {title: "Hardcoded", oneOf: [...]}
        structure produced by transform_schema.

        Returns (list of {value, display}, warnings).
        """
        any_of = field_schema.get("anyOf", [])
        hardcoded_choices: List[Dict[str, str]] = []

        if not any_of:
            return [], []

        for option in any_of:
            # Skip $ref entries (already pointing to existing choice list)
            if "$ref" in option:
                return [], []

            # Look for hardcoded oneOf structure
            one_of = option.get("oneOf", [])
            if one_of and option.get("title") == "Hardcoded":
                hardcoded_choices.extend(
                    [{"value": item["const"], "display": item.get("title", item["const"])} for item in one_of]
                )

        if not hardcoded_choices:
            return [], []

        # Deduplication tracking
        seen: Dict[str, str] = {}
        warnings: List[str] = []
        deduplicated_choices: List[Dict[str, str]] = []

        for choice in hardcoded_choices:
            if choice["value"] in seen:
                warnings.append(
                    f"Duplicate choice value '{choice['value']}' found in field. "
                    f"Keeping first occurrence with display '{seen[choice['value']]}', "
                    f"dropping subsequent with display '{choice['display']}'."
                )
            else:
                seen[choice["value"]] = choice["display"]
                deduplicated_choices.append(choice)

        return deduplicated_choices, warnings

    @staticmethod
    def _update_summary(summary: Dict[str, int], status: str) -> None:
        status_map = {
            "matched": "matched",
            "candidate": "candidate",
            "to_create": "to_create",
            "created": "created",
            "error": "errors",
        }
        key = status_map.get(status)
        if key:
            summary[key] += 1

    def rewrite_field_to_ref(self, field_schema: Dict[str, Any], choice_field_name: str) -> None:
        """Replace hardcoded anyOf/oneOf with a $ref to the choices endpoint. Mutates in-place."""
        ref_url = f"{self.choices_base_url}?field={choice_field_name}"
        field_schema["anyOf"] = [{"$ref": ref_url}]

    def process_choices_single_field(
        self,
        field_name: str,
        field_schema: Dict[str, Any],
        hardcoded_choices: List[Dict[str, str]],
        reserved_names: Optional[set] = None,
    ) -> ChoiceFieldResult:
        """Analyze a single field: match against existing/proposed choices or propose a new name."""
        result = ChoiceFieldResult(field_name=field_name, choices=hardcoded_choices)

        # 1. Try to find matching existing choice field (DB + proposed)
        match = self.find_matching_choice_field(field_name, hardcoded_choices)

        if match:
            existing_field_name, score, missing_values = match
            result.existing_choice_field = existing_field_name
            result.match_score = score
            result.choices_to_add = missing_values

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
        proposed_name = self.generate_unique_name(field_name, field_schema, reserved_names=reserved_names or set())
        result.proposed_name = proposed_name
        result.status = "to_create"
        logger.info(
            "Field '%s' will create new choice field '%s'",
            field_name,
            proposed_name,
        )

        return result

    def normalize_for_matching(self, value: str) -> str:
        """Lowercase and collapse separators to a single dash for fuzzy comparison."""
        normalized = value.lower()
        normalized = self.SEPARATOR_PATTERN.sub("-", normalized)
        return normalized.strip("-")

    def slugify_for_choice(self, value: str) -> str:
        """Convert a string to a valid choice field name (lowercase, underscores only)."""
        slugified = value.lower()
        slugified = re.sub(r"[^a-z0-9]+", "_", slugified)
        slugified = re.sub(r"_+", "_", slugified)
        return slugified.strip("_")

    def find_matching_choice_field(
        self,
        field_name: str,
        field_hardcoded_choices: List[Dict[str, str]],
    ) -> Optional[Tuple[str, float, List[Dict[str, str]]]]:
        """Find an existing or proposed choice field matching the hardcoded values.

        Uses Jaccard similarity on normalized values for treshhold comparison and name-match for real comparison.
        Returns (field_name, score, missing_values) or None.
        """
        # Build normalized -> original mapping for hardcoded values
        hardcoded_by_normalized = {self.normalize_for_matching(v["value"]): v for v in field_hardcoded_choices}
        hardcoded_normalized_values = set(hardcoded_by_normalized.keys())
        hardcoded_values = [v["value"] for v in field_hardcoded_choices]

        all_choice_fields = self.existing_choices.copy()

        # Merge proposed choices into existing fields for matching
        if self.proposed_choices:
            for proposed_name, proposed_values in self.proposed_choices.items():
                if proposed_name not in all_choice_fields:
                    all_choice_fields[proposed_name] = proposed_values

        best_match: Optional[Tuple[str, float, List[Dict[str, str]]]] = None

        for existing_field_name, existing_values in all_choice_fields.items():
            # Normalize existing values for comparison
            existing_normalized_values = {self.normalize_for_matching(v) for v in existing_values}

            if not existing_normalized_values:
                continue

            # Calculate overlap score (Jaccard similarity)
            # using normalized values
            intersection = hardcoded_normalized_values & existing_normalized_values
            union = hardcoded_normalized_values | existing_normalized_values
            normalized_score = len(intersection) / len(union) if union else 0.0
            # using original values
            intersection = set(hardcoded_values) & set(existing_values)
            union = set(hardcoded_values) | set(existing_values)
            value_score = len(intersection) / len(union) if union else 0.0

            # Early exit if with first exact match on actual values
            if value_score == 1.0:
                best_match = (existing_field_name, value_score, [])
                break

            if normalized_score >= self.MATCH_THRESHOLD:
                # Find missing values (in hardcoded but not in existing)
                missing_values = set(hardcoded_values) - set(existing_values)
                missing_choices = [hardcoded_by_normalized[self.normalize_for_matching(v)] for v in missing_values]

                if best_match is None or value_score > best_match[1]:
                    best_match = (existing_field_name, value_score, missing_choices)

        return best_match

    def generate_unique_name(
        self, field_name: str, field_schema: Dict[str, Any], reserved_names: set = frozenset()
    ) -> str:
        """Generate a unique choice field name.

        Tries: field_name, field title, event_type + field_name, then numeric suffix.
        Checks against existing_choices and reserved_names (current batch).
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

        # Check against both DB names and batch-reserved names
        existing_names = set(self.existing_choices.keys()) | set(reserved_names)

        # Try each candidate
        for candidate in candidates:
            if candidate not in existing_names:
                return candidate

        # All candidates taken - add numeric suffix
        base_name = candidates[0]
        counter = 1
        while True:
            name = f"{base_name}_{counter}"
            if name not in existing_names:
                return name
            counter += 1

    def create_choice_field(self, field_name: str, values: List[Dict[str, str]]) -> None:
        """Create Choice objects for a new choice field."""
        seen_values = set()
        ordernum = 0
        for item in values:
            value = item.get("value")
            if not value:
                logger.warning("Skipping empty value in choice field '%s'", field_name)
                continue

            if value in seen_values:
                continue

            seen_values.add(value)

            Choice.objects.create(
                model=Choice.EVENT_MODEL,
                field=field_name,
                value=value,
                display=item.get("display", value),
                ordernum=ordernum,
            )

            ordernum += 1

    def add_values_to_choice_field(self, field_name: str, values: List[Dict[str, str]]) -> int:
        """Add missing values to an existing choice field. Returns count added."""
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
