"""Hardcoded choice processing for migrated V2 schemas."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from django.db import models

from choices.models import Choice

from .utils import normalize_for_matching, slugify_for_choice, smart_abbreviate

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
    choice_field_name: str
    missing_choices: list[dict[str, str]] | None = None
    property_path: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> HardcodedChoiceResolution:
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
    property_path: list[str] = field(default_factory=list)
    choices: list[dict[str, str]] = field(default_factory=list)
    resolution_options: list[HardcodedChoiceResolution] = field(default_factory=list)

    def needs_resolution(self) -> bool:
        """
        Determines if the hardcoded choice needs a resolution specified by the user.
        """
        for resolution in self.resolution_options:
            if resolution.strategy in [
                ResolutionStrategy.MERGE_INTO_EXISTING,
                ResolutionStrategy.MERGE_INTO_PROPOSED,
            ]:
                return True

        return False


class ChoiceProcessor:
    """Detects inline choice values in V2 schemas and matches them against
    existing Choice objects and proposed choices from the current batch.

    Statuses: matched (100%), candidate (partial, blocks migration), to_create (new).
    """

    # Minimum overlap ratio to consider an existing (or proposed) choice field a "match"
    MATCH_THRESHOLD = 2 / 3

    def __init__(self):
        self.event_type_value: str = ""
        self.proposed_choices: dict[str, list[str]] = {}
        self.existing_choices: dict[str, list[str]] = {}

    def normalize_for_matching(self, value: str) -> str:
        return normalize_for_matching(value)

    def get_hardcoded_choices(self, v2_schema: dict) -> list[HardcodedChoice]:
        """Analyze all fields, builds a data structure with the results."""
        return self._collect_hardcoded_choices_from_properties(v2_schema.get("json", {}).get("properties", {}), [])

    def _collect_hardcoded_choices_from_properties(
        self, properties: dict, current_path: list[str]
    ) -> list[HardcodedChoice]:
        """
        Recursively traverse properties to find hardcoded choices.
        """
        hardcoded_choices: list[HardcodedChoice] = []

        for field_name, field_schema in properties.items():
            if field_schema.get("type") == "array":
                collection_properties = field_schema.get("items", {}).get("properties", {})
                if not collection_properties:
                    continue
                path = current_path + [field_name]
                hardcoded_choices.extend(self._collect_hardcoded_choices_from_properties(collection_properties, path))
                continue

            # Note: "type" == "object" doesn't "exist" in v1 schemas, at least not officially
            field_hardcoded_choices = self.extract_field_hardcoded_choices(field_schema)
            if not field_hardcoded_choices:
                continue

            hardcoded_choices.append(
                HardcodedChoice(property_path=current_path + [field_name], choices=field_hardcoded_choices)
            )

        return hardcoded_choices

    def extract_field_hardcoded_choices(self, field_schema: dict) -> list[dict]:
        """Extract hardcoded choices from anyOf > {title: "Hardcoded", oneOf: [...]}
        structure produced by transform_schema.

        Returns (list of {value, display}).
        """
        hardcoded_choices: list[dict] = []
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
        deduplicated_choices: list[dict] = []

        for choice in hardcoded_choices:
            if choice["value"] not in seen:
                seen[choice["value"]] = choice["display"]
                deduplicated_choices.append(choice)

        return deduplicated_choices

    def populate_resolution_options(
        self,
        results,
        existing_choices: dict[str, list[str]],
        proposed_choices: dict[str, list[str]],
    ):
        """Analyze migration results and determine choice resolutions."""
        self.existing_choices = existing_choices
        self.proposed_choices = proposed_choices

        for result in results:
            if not result.success or not result.hardcoded_choices:
                continue
            for hardcoded_choice in result.hardcoded_choices:
                hardcoded_choice.resolution_options = self.get_resolution_options(result, hardcoded_choice)
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

    def find_matching_resolution_option(
        self, hardcoded_choice: HardcodedChoice, selection: HardcodedChoiceResolution
    ) -> HardcodedChoiceResolution | None:
        for option in hardcoded_choice.resolution_options:
            if self._selected_resolution_matches_option(selection, option):
                return option

        return None

    def _selected_resolution_matches_option(
        self, selection: HardcodedChoiceResolution, option: HardcodedChoiceResolution
    ) -> bool:
        if selection.strategy == ResolutionStrategy.CREATE_NEW:
            return selection.property_path == option.property_path and selection.strategy == option.strategy
        return (
            selection.property_path == option.property_path
            and selection.strategy == option.strategy
            and selection.choice_field_name == option.choice_field_name
        )

    def get_resolution_options(
        self, migration_result, hardcoded_choice: HardcodedChoice
    ) -> list[HardcodedChoiceResolution]:
        """Analyze possible choice resolutions for a migration result."""
        # We rely on the phase 1 and that the migration_result has the hardcoded_choices attribute already populated
        # First we atempt to find a perfect match in the existing choices
        # Then we attempt to find a perfect match in the proposed choices
        # If no perfect match is found, we propose to merge against one existing or proposed choice field

        # Finally we propose a new choice field name, indeed it's always possible to create a new choice field
        # For create new we automatically propose a choice field name that is unique

        resolutions = []

        existing_match = self.find_best_matching_choice_field(hardcoded_choice, self.existing_choices)
        proposed_match = self.find_best_matching_choice_field(hardcoded_choice, self.proposed_choices)

        existing_score = existing_match[1] if existing_match else 0.0
        proposed_score = proposed_match[1] if proposed_match else 0.0

        if (existing_match and existing_score == 1.0) or proposed_score == 1.0:
            # Perfect match found
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

        proposed_name = self.generate_unique_choice_field_name(
            hardcoded_choice.property_path,
            migration_result.event_type_value,
        )
        create_resolution = HardcodedChoiceResolution(
            strategy=ResolutionStrategy.CREATE_NEW,
            choice_field_name=proposed_name,
            property_path=list(hardcoded_choice.property_path),
        )
        resolutions.append(create_resolution)

        if not existing_match and not proposed_match:
            # No match found, return just the create resolution
            return resolutions

        if existing_match and existing_score >= proposed_score and existing_score < 1.0:
            match_field_name, score, missing_choices = existing_match
            resolution = HardcodedChoiceResolution(
                strategy=ResolutionStrategy.MERGE_INTO_EXISTING,
                choice_field_name=match_field_name,
                missing_choices=missing_choices,
                property_path=list(hardcoded_choice.property_path),
            )
            resolutions.append(resolution)

        if proposed_match and proposed_score > existing_score and proposed_score < 1.0:
            match_field_name, score, missing_choices = proposed_match
            resolution = HardcodedChoiceResolution(
                strategy=ResolutionStrategy.MERGE_INTO_PROPOSED,
                choice_field_name=match_field_name,
                missing_choices=missing_choices,
                property_path=list(hardcoded_choice.property_path),
            )
            resolutions.append(resolution)

        return resolutions

    def find_best_matching_choice_field(
        self,
        hardcoded_choice: HardcodedChoice,
        against_values: dict[str, list[str]],  # just a dict of lists of values, not the full choice objects
    ) -> tuple[str, float, list[dict[str, str]]] | None:
        """Find an the best match choice field for the given hardcoded choices.

        Uses Jaccard similarity on normalized values for treshhold comparison and name-match for real comparison.
        Returns (choice_field_name, score, missing_values) or None.
        """
        # Build normalized -> original mapping for hardcoded values
        hardcoded_by_normalized = {normalize_for_matching(v["value"]): v for v in hardcoded_choice.choices}
        hardcoded_normalized_values = set(hardcoded_by_normalized.keys())
        hardcoded_values = {v["value"] for v in hardcoded_choice.choices}

        against_values = against_values.copy()

        best_match: tuple[str, float, list[dict[str, str]]] | None = None

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

    def generate_unique_choice_field_name(self, field_path: list[str], event_type_value: str) -> str:
        """Generate a unique choice field name, strictly bounded to 40 chars.

        Tries: field_name, path, event_type + field_name, event_type + path.
        Applies 'smart' vowel abbreviation if length > 40.
        Adds numeric suffix on collision, truncating base further if needed.
        Checks against existing_choices and reserved_names (current batch).
        """
        raw_candidates = []

        reserved_names = set()
        reserved_names.update(self.existing_choices.keys())
        reserved_names.update(self.proposed_choices.keys())

        # Candidate 1: field name directly
        raw_candidates.append(slugify_for_choice(field_path[-1]))
        if len(field_path) > 1:
            raw_candidates.append(slugify_for_choice("_".join(field_path)))

        # Candidate 2: event_type + field_name
        if event_type_value:
            raw_candidates.append(slugify_for_choice(f"{event_type_value}_{field_path[-1]}"))
            if len(field_path) > 1:
                raw_candidates.append(slugify_for_choice(f"{event_type_value}_{'_'.join(field_path)}"))

        # Apply abbreviation and filter unique ordered candidates
        candidates = []
        for raw in raw_candidates:
            # We target 40 but realistically we might need room for suffixes.
            # A 40 char limit is fine for the base try.
            abbrev = smart_abbreviate(raw, max_length=40)
            if abbrev not in candidates:
                candidates.append(abbrev)

        # Try each candidate without suffix
        for candidate in candidates:
            if candidate not in reserved_names:
                return candidate

        # All candidates taken
        base_name = candidates[0]
        counter = 1
        while True:
            suffix = f"_{counter}"
            max_base_len = 40 - len(suffix)
            # Truncate base to allow suffix to fit
            truncated_base = base_name[:max_base_len].rstrip("_")
            name = f"{truncated_base}{suffix}"
            if name not in reserved_names:
                return name
            counter += 1

    def create_choice_field(self, field_name: str, values: list[dict[str, str]]) -> None:
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

    def add_values_to_choice_field(self, field_name: str, values: list[dict[str, str]]) -> int:
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
