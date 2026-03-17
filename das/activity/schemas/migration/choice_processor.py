"""Hardcoded choice processing for migrated V2 schemas."""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from django.db import models
from django.urls import reverse

from choices.models import Choice

logger = logging.getLogger(__name__)


class ResolutionStrategy(str, Enum):
    CREATE_NEW = "CREATE_NEW"
    USE_EXISTING = "USE_EXISTING"
    USE_PROPOSED = "USE_PROPOSED"
    MERGE_INTO_EXISTING = "MERGE_INTO_EXISTING"
    MERGE_INTO_PROPOSED = "MERGE_INTO_PROPOSED"


@dataclass
class HardcodedChoiceResolution:
    strategy: ResolutionStrategy
    choice_field_name: Optional[str] = None
    missing_choices: Optional[List[Dict[str, str]]] = None
    property_path: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "HardcodedChoiceResolution":
        normalized_data = data.copy()
        strategy = normalized_data.get("strategy")
        if not isinstance(strategy, ResolutionStrategy):
            normalized_data["strategy"] = ResolutionStrategy(strategy)
        property_path = normalized_data.get("property_path")
        if property_path is not None:
            normalized_data["property_path"] = list(property_path)

        return cls(**normalized_data)


@dataclass
class HardcodedChoice:
    property_path: List[str]
    choices: List[Dict[str, str]] = field(default_factory=list)
    resolution_options: List[HardcodedChoiceResolution] = field(default_factory=list)

    def needs_resolution(self) -> bool:
        """
        Determines if the hardcoded choice needs a resolution specified by the user.
        """
        if len(self.resolution_options) > 1:
            return True

        if len(self.resolution_options) == 1 and self.resolution_options[0].strategy in [
            ResolutionStrategy.CREATE_NEW,
            ResolutionStrategy.USE_EXISTING,
            ResolutionStrategy.USE_PROPOSED,
        ]:
            # If we have a single resolution with one of these strategies,
            # we don't need a user to specify it, we can handle it automatically
            return False

        # Resolutions should always be defined, otherwise we can't process the choice
        if not self.resolution_options:
            raise ValueError("No resolution options defined for hardcoded choice")

        raise ValueError(f"Invalid resolution strategy: {self.resolution_options[0].strategy}")


def get_field_schema_from_prop_path(v2_schema: Dict[str, Any], prop_path: List[str]) -> Dict[str, Any]:
    """Get the field schema from a property path."""
    current_properties = v2_schema.get("json", {}).get("properties", {})
    field_schema: Dict[str, Any] | None = None

    for index, field_name in enumerate(prop_path):
        field_schema = current_properties[field_name]
        if index == len(prop_path) - 1:
            return field_schema

        if field_schema.get("type") == "array":
            current_properties = field_schema.get("items", {}).get("properties", {})
            continue

        current_properties = field_schema.get("properties", {})

    raise KeyError(f"Invalid property path: {prop_path}")


def rewrite_field_to_ref(field_schema: Dict[str, Any], choice_field_name: str) -> None:
    """Replace hardcoded anyOf/oneOf with a $ref to the choices endpoint. Mutates in-place."""
    ref_url = f"{reverse('schemas:choices')}?field={choice_field_name}"
    field_schema["anyOf"] = [{"$ref": ref_url}]


def normalize_for_matching(value: str) -> str:
    """Lowercase and collapse separators to a single dash for fuzzy comparison."""
    # Separator normalization pattern for matching
    SEPARATOR_PATTERN = re.compile(r"[-_.\s]+")
    normalized = value.lower()
    normalized = SEPARATOR_PATTERN.sub("-", normalized)
    return normalized.strip("-")


def slugify_for_choice(value: str) -> str:
    """Convert a string to a valid choice field name (lowercase, underscores only)."""
    slugified = value.lower()
    slugified = re.sub(r"[^a-z0-9]+", "_", slugified)
    slugified = re.sub(r"_+", "_", slugified)
    return slugified.strip("_")


class ChoiceProcessor:
    """Detects inline choice values in V2 schemas and matches them against
    existing Choice objects and proposed choices from the current batch.

    Statuses: matched (100%), candidate (partial, blocks migration), to_create (new).
    """

    # Minimum overlap ratio to consider an existing (or proposed) choice field a "match"
    MATCH_THRESHOLD = 2 / 3

    def __init__(
        self,
        event_type_value: str = "",
        choices_base_url: str | None = None,
        proposed_choices: Optional[Dict[str, List[str]]] = None,
        existing_choices: Optional[Dict[str, List[str]]] = None,
    ):
        self.event_type_value = event_type_value
        self.proposed_choices = proposed_choices or {}
        self.existing_choices = existing_choices or {}
        if choices_base_url is not None:
            self._choices_base_url = choices_base_url

    @property
    def choices_base_url(self):
        if not hasattr(self, "_choices_base_url"):
            self._choices_base_url = reverse("schemas:choices")
        return self._choices_base_url

    def normalize_for_matching(self, value: str) -> str:
        return normalize_for_matching(value)

    def get_hardcoded_choices(self, v2_schema: dict) -> List[HardcodedChoice]:
        """Analyze all fields, builds a data structure with the results."""
        return self.traverse_properties(v2_schema.get("json", {}).get("properties", {}), [])

    def traverse_properties(self, properties: dict, current_path: List[str]) -> List[HardcodedChoice]:
        """
        Recursively traverse properties to find hardcoded choices.

        Returns:
            List of tuples (path, hardcoded_choices) where:
            - path is a list of field names (property path from root)
            - hardcoded_choices is a list of choice definitions
        """
        hardcoded_choices: List[HardcodedChoice] = []

        for field_name, field_schema in properties.items():
            if field_schema.get("type") == "array":
                collection_properties = field_schema.get("items", {}).get("properties", {})
                if not collection_properties:
                    continue
                path = current_path + [field_name]
                hardcoded_choices.extend(self.traverse_properties(collection_properties, path))
                continue

            field_hardcoded_choices = self.extract_hardcoded_choices(field_schema)
            if not field_hardcoded_choices:
                continue

            hardcoded_choices.append(
                HardcodedChoice(property_path=current_path + [field_name], choices=field_hardcoded_choices)
            )

        return hardcoded_choices

    def extract_hardcoded_choices(self, field_schema: dict) -> List[dict]:
        """Extract hardcoded choices from anyOf > {title: "Hardcoded", oneOf: [...]}
        structure produced by transform_schema.

        Returns (list of {value, display}).
        """
        hardcoded_choices: List[dict] = []
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
                hardcoded_choices.extend(
                    [{"value": item["const"], "display": item.get("title", item["const"])} for item in one_of]
                )

        # Deduplication
        seen = {}
        deduplicated_choices: List[dict] = []

        for choice in hardcoded_choices:
            if choice["value"] not in seen:
                seen[choice["value"]] = choice["display"]
                deduplicated_choices.append(choice)

        return deduplicated_choices

    def analyze_migration_results(
        self,
        results,
        existing_choices: Dict[str, List[str]],
        proposed_choices: Dict[str, List[str]],
    ):
        """Analyze migration results and determine choice resolutions."""
        self.existing_choices = existing_choices
        self.proposed_choices = proposed_choices
        self.created_choices = []

        for result in results:
            if not result.success or not result.hardcoded_choices:
                continue
            for hardcoded_choice in result.hardcoded_choices:
                hardcoded_choice.resolution_options = self.get_possible_choice_resolutions(result, hardcoded_choice)
                create_resolution = next(
                    (
                        option
                        for option in hardcoded_choice.resolution_options
                        if option.strategy == ResolutionStrategy.CREATE_NEW and option.choice_field_name
                    ),
                    None,
                )
                if create_resolution is not None:
                    self.proposed_choices.setdefault(
                        create_resolution.choice_field_name,
                        [choice["value"] for choice in hardcoded_choice.choices],
                    )

    def resolution_matches_option(
        self,
        selection: HardcodedChoiceResolution,
        option: HardcodedChoiceResolution,
    ) -> bool:
        if selection.strategy == ResolutionStrategy.CREATE_NEW:
            return selection.property_path == option.property_path and selection.strategy == option.strategy
        return (
            selection.property_path == option.property_path
            and selection.strategy == option.strategy
            and selection.choice_field_name == option.choice_field_name
        )

    def find_matching_resolution_option(
        self,
        hardcoded_choice: HardcodedChoice,
        selection: HardcodedChoiceResolution,
    ) -> Optional[HardcodedChoiceResolution]:
        for option in hardcoded_choice.resolution_options:
            if self.resolution_matches_option(selection, option):
                return option

        return None

    def get_possible_choice_resolutions(
        self, migration_result, hardcoded_choice: HardcodedChoice
    ) -> List[HardcodedChoiceResolution]:
        """Analyze possible choice resolutions for a migration result."""
        # We rely on the phase 1 and that the migration_result has the hardcoded_choices attribute already populated
        # First we atempt to find a perfect match in the existing choices
        # Then we attempt to find a perfect match in the proposed choices
        # If no perfect match is found, we propose to merge against one existing or proposed choice field

        # Finally we propose a new choice field name, indeed it's always possible to create a new choice field
        # For create new we automatically propose a choice field name that is unique

        resolutions = []

        existing_match = self.find_matching_choice_field(hardcoded_choice, self.existing_choices)
        proposed_match = self.find_matching_choice_field(hardcoded_choice, self.proposed_choices)

        existing_score = existing_match[1] if existing_match else 0.0
        proposed_score = proposed_match[1] if proposed_match else 0.0

        if existing_score == 1.0 or proposed_score == 1.0:
            # Perfect match found, no need to propose anything
            if existing_score == 1.0:
                strategy = ResolutionStrategy.USE_EXISTING
                choice_field_name = existing_match[0]
            else:
                # in case of proposed match, we depend on successful creation
                strategy = ResolutionStrategy.USE_PROPOSED
                choice_field_name = proposed_match[0]

            resolution = HardcodedChoiceResolution(
                strategy=strategy,
                choice_field_name=choice_field_name,
                property_path=list(hardcoded_choice.property_path),
            )
            resolutions.append(resolution)
            return resolutions

        proposed_name = self.generate_unique_name(hardcoded_choice.property_path, migration_result.event_type_value)
        create_resolution = HardcodedChoiceResolution(
            strategy=ResolutionStrategy.CREATE_NEW,
            choice_field_name=proposed_name,
            property_path=list(hardcoded_choice.property_path),
        )
        resolutions.append(create_resolution)

        if not existing_match and not proposed_match:
            # No match found, return just the create resolution
            return resolutions

        if existing_match and existing_score >= proposed_score:
            match_field_name, score, missing_choices = existing_match
            resolution = HardcodedChoiceResolution(
                strategy=ResolutionStrategy.MERGE_INTO_EXISTING,
                choice_field_name=match_field_name,
                missing_choices=missing_choices,
                property_path=list(hardcoded_choice.property_path),
            )
            resolutions.append(resolution)

        if proposed_match and proposed_score > existing_score:
            match_field_name, score, missing_choices = proposed_match
            resolution = HardcodedChoiceResolution(
                strategy=ResolutionStrategy.MERGE_INTO_PROPOSED,
                choice_field_name=match_field_name,
                missing_choices=missing_choices,
                property_path=list(hardcoded_choice.property_path),
            )
            resolutions.append(resolution)

        return resolutions

    def find_matching_choice_field(
        self,
        hardcoded_choice: HardcodedChoice,
        against_values: Dict[str, List[str]],  # just a dict of lists of values, not the full choice objects
    ) -> Optional[Tuple[str, float, List[Dict[str, str]]]]:
        """Find an the best match choice field for the given hardcoded choices.

        Uses Jaccard similarity on normalized values for treshhold comparison and name-match for real comparison.
        Returns (choice_field_name, score, missing_values) or None.
        """
        # Build normalized -> original mapping for hardcoded values
        hardcoded_by_normalized = {normalize_for_matching(v["value"]): v for v in hardcoded_choice.choices}
        hardcoded_normalized_values = set(hardcoded_by_normalized.keys())
        hardcoded_values = {v["value"] for v in hardcoded_choice.choices}

        against_values = against_values.copy()

        best_match: Optional[Tuple[str, float, List[Dict[str, str]]]] = None

        for choice_field_name, values in against_values.items():
            # Normalize existing values for comparison
            normalized_values = {normalize_for_matching(v) for v in values}

            # Calculate overlap score (Jaccard similarity)
            # using normalized values
            intersection = hardcoded_normalized_values & normalized_values
            union = hardcoded_normalized_values | normalized_values
            normalized_score = len(intersection) / len(union)
            # using original values
            intersection = hardcoded_values & set(values)
            union = hardcoded_values | set(values)
            value_score = len(intersection) / len(union)

            # Early exit if with first exact match on actual values
            if value_score == 1.0:
                best_match = (choice_field_name, value_score, [])
                break

            if normalized_score >= self.MATCH_THRESHOLD:
                # Find missing values (in hardcoded but not in existing)
                missing_values = hardcoded_values - set(values)
                missing_choices = [hardcoded_by_normalized[normalize_for_matching(v)] for v in missing_values]

                if best_match is None or value_score > best_match[1]:
                    best_match = (choice_field_name, value_score, missing_choices)

        return best_match

    def generate_unique_name(self, field_path: List[str], event_type_value: str) -> str:
        """Generate a unique choice field name.

        Tries: field_name, event_type + field_name, then numeric suffix.
        Checks against existing_choices and reserved_names (current batch).
        """
        candidates = []
        reserved_names = self.existing_choices.keys() | self.proposed_choices.keys()

        # Candidate 1: field name directly
        candidates.append(slugify_for_choice(field_path[-1]))
        if len(field_path) > 1:
            candidates.append(slugify_for_choice("_".join(field_path)))

        # Candidate 2: event_type + field_name
        if event_type_value:
            candidates.append(slugify_for_choice(f"{event_type_value}_{field_path[-1]}"))
            if len(field_path) > 1:
                candidates.append(slugify_for_choice(f"{event_type_value}_{'_'.join(field_path)}"))

        # Try each candidate
        for candidate in candidates:
            if candidate not in reserved_names:
                return candidate

        # All candidates taken - add numeric suffix
        base_name = candidates[0]
        counter = 1
        while True:
            name = f"{base_name}_{counter}"
            if name not in reserved_names:
                return name
            counter += 1

    def persist_hardcoded_choices(self, event_type, result) -> None:
        """Persist hardcoded choices for an event type."""
        for field_name, values in result.hardcoded_choices.items():
            self.create_choice_field(field_name, values)

    def create_choice_field(self, field_name: str, values: List[Dict[str, str]]) -> None:
        """Create Choice objects for a new choice field."""
        seen_values = set()
        ordernum = 0
        choices_to_create = []
        for item in values:
            value = item.get("value")
            if not value:
                logger.warning("Skipping empty value in choice field '%s'", field_name)
                continue

            if value in seen_values:
                continue

            seen_values.add(value)

            choices_to_create.append(
                Choice(
                    model=Choice.EVENT_MODEL,
                    field=field_name,
                    value=value,
                    display=item.get("display", value),
                    ordernum=ordernum,
                )
            )

            ordernum += 1

        if choices_to_create:
            Choice.objects.bulk_create(choices_to_create)

    def add_values_to_choice_field(self, field_name: str, values: List[Dict[str, str]]) -> int:
        """Add missing values to an existing choice field. Returns count added."""
        # Get next ordernum for this field
        max_order = Choice.objects.filter(model=Choice.EVENT_MODEL, field=field_name).aggregate(
            max_order=models.Max("ordernum")
        )["max_order"]
        next_order = (max_order or 0) + 1
        existing_values = set(
            Choice.objects.filter(model=Choice.EVENT_MODEL, field=field_name).values_list("value", flat=True)
        )
        choices_to_create = []

        for item in values:
            value = item["value"]
            if not value:
                continue

            if value in existing_values:
                continue

            existing_values.add(value)
            choices_to_create.append(
                Choice(
                    model=Choice.EVENT_MODEL,
                    field=field_name,
                    value=value,
                    display=item.get("display", value),
                    ordernum=next_order,
                )
            )
            next_order += 1

        if choices_to_create:
            Choice.objects.bulk_create(choices_to_create)

        return len(choices_to_create)
