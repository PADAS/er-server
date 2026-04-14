"""Hardcoded choice processing for migrated V2 schemas."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from choices.models import Choice

from .utils import slugify_for_choice, smart_abbreviate

logger = logging.getLogger(__name__)


class ResolutionStrategy(str, Enum):
    CREATE_NEW = "CREATE_NEW"
    USE_EXISTING = "USE_EXISTING"
    USE_PROPOSED = "USE_PROPOSED"


@dataclass
class HardcodedChoiceResolution:
    strategy: ResolutionStrategy
    choice_field_name: str
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


class ChoiceProcessor:
    """Detects inline choice values in V2 schemas and matches them against
    existing Choice objects and proposed choices from the current batch.

    Resolution: exact match → USE_EXISTING / USE_PROPOSED, otherwise → CREATE_NEW.
    """

    def __init__(self):
        self.proposed_choices: dict[str, list[str]] = {}
        self.existing_choices: dict[str, list[str]] = {}

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
            field_hardcoded_choices = self._extract_field_hardcoded_choices(field_schema)
            if not field_hardcoded_choices:
                continue

            hardcoded_choices.append(
                HardcodedChoice(property_path=current_path + [field_name], choices=field_hardcoded_choices)
            )

        return hardcoded_choices

    def _extract_field_hardcoded_choices(self, field_schema: dict) -> list[dict]:
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
        # First we attempt to find a perfect match in existing or proposed choices.
        # CREATE_NEW is always offered as an option.

        resolutions = []

        existing_match = self.find_exact_matching_choice_field(hardcoded_choice, self.existing_choices)
        proposed_match = self.find_exact_matching_choice_field(hardcoded_choice, self.proposed_choices)

        if existing_match:
            resolutions.append(
                HardcodedChoiceResolution(
                    strategy=ResolutionStrategy.USE_EXISTING,
                    choice_field_name=existing_match,
                    property_path=list(hardcoded_choice.property_path),
                )
            )
        elif proposed_match:
            resolutions.append(
                HardcodedChoiceResolution(
                    strategy=ResolutionStrategy.USE_PROPOSED,
                    choice_field_name=proposed_match,
                    property_path=list(hardcoded_choice.property_path),
                )
            )

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

        return resolutions

    def find_exact_matching_choice_field(
        self,
        hardcoded_choice: HardcodedChoice,
        against_values: dict[str, list[str]],
    ) -> str | None:
        """Find a choice field whose values exactly match the hardcoded choices.

        Returns the choice field name or None.
        """
        hardcoded_values = {v["value"] for v in hardcoded_choice.choices}

        for choice_field_name, values in against_values.items():
            if hardcoded_values == set(values):
                return choice_field_name

        return None

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
