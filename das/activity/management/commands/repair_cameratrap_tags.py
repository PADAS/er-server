from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from activity.models import EventType
from choices.models import Choice
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)

# Known-good JSON schema property for `tags` (the array/choice-list shape).
GOOD_TAGS_JSON_PROPERTY: Final[dict] = {
    "title": "Tags",
    "type": "array",
    "description": "",
    "items": {
        "type": "string",
        "anyOf": [{"$ref": "/api/v2.0/schemas/choices.json?field=cameratrap_tags"}],
    },
    "deprecated": False,
    "uniqueItems": True,
}

# Known-good UI field config for `tags` (CHOICE_LIST shape, parent is
# intentionally overridden at runtime to preserve the tenant's existing layout).
GOOD_TAGS_UI_FIELD_BASE: Final[dict] = {
    "choices": {
        "eventTypeCategories": [],
        "existingChoiceList": ["cameratrap_tags"],
        "featureCategories": [],
        "myDataType": "EVENT_TYPES_FROM_EVENT_CATEGORY",
        "subjectGroups": [],
        "subjectSubtypes": [],
        "type": "EXISTING_CHOICE_LIST",
    },
    "inputType": "LIST",
    "placeholder": "",
    "type": "CHOICE_LIST",
}

# Last-resort parent section name used when no existing section can be
# determined from the schema; "section-2" is the conventional details
# section in known-good cameratrap schemas.
FALLBACK_PARENT_SECTION: Final[str] = "section-2"

# Known-good V1 schema property for `tags` (the choice-list reference shape).
GOOD_TAGS_V1_SCHEMA_PROPERTY: Final[dict] = {"key": "tags"}

# Known-good V1 form `definition` entry for `tags`.
GOOD_TAGS_V1_DEFINITION_ENTRY: Final[dict] = {
    "key": "tags",
    "type": "checkboxes",
    "htmlClass": "d-none",
    "title": "Tags",
    "titleMap": "{{enum___cameratrap_tags___map}}",
}

# Known-good V2 JSON schema property for `tag_count_array` (Detections array).
# Taken verbatim from cameratrap_rep.json json.properties.tag_count_array.
GOOD_TAG_COUNT_ARRAY_JSON_PROPERTY: Final[dict] = {
    "title": "Detections",
    "type": "array",
    "description": "",
    "items": {
        "unevaluatedProperties": False,
        "properties": {
            "tag": {
                "title": "Tag",
                "type": "string",
                "description": "",
                "deprecated": False,
            },
            "count": {
                "title": "Count",
                "type": "number",
                "description": "",
                "deprecated": False,
            },
        },
        "required": [],
        "type": "object",
    },
    "unevaluatedItems": False,
    "deprecated": False,
}

# Known-good V2 UI field for the `tag_count_array` COLLECTION.
# Parent is overridden at runtime to preserve the tenant's section layout
# (same approach as GOOD_TAGS_UI_FIELD_BASE).
GOOD_TAG_COUNT_ARRAY_UI_FIELD: Final[dict] = {
    "buttonText": "Add",
    "columns": 1,
    "itemIdentifier": "",
    "itemName": "Detection",
    "leftColumn": ["tag", "count"],
    "rightColumn": [],
    "type": "COLLECTION",
}

# Known-good V2 UI field for the `tag` sub-field of the collection.
GOOD_TAG_UI_FIELD: Final[dict] = {
    "inputType": "SHORT_TEXT",
    "parent": "tag_count_array",
    "placeholder": "",
    "type": "TEXT",
}

# Known-good V2 UI field for the `count` sub-field of the collection.
GOOD_COUNT_UI_FIELD: Final[dict] = {
    "parent": "tag_count_array",
    "placeholder": "",
    "type": "NUMERIC",
}

# Known-good V1 schema property for `tag_count_array`.
# Taken verbatim from cameratrap_rep.v1 schema.properties.tag_count_array.
GOOD_TAG_COUNT_ARRAY_V1_SCHEMA_PROPERTY: Final[dict] = {
    "type": "array",
    "title": "Detections",
    "items": {
        "type": "object",
        "title": "Detection",
        "properties": {
            "tag": {"type": "string", "title": "Tag"},
            "count": {"type": "number", "title": "Count"},
        },
    },
}

# Known-good V1 form `definition` entry for `tag_count_array`.
GOOD_TAG_COUNT_ARRAY_V1_DEFINITION_ENTRY: Final[dict] = {"key": "tag_count_array"}

_CHOICES_FIXTURE_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "fixtures" / "eventtypes" / "cameratrap_rep_choices.json"  # das/activity/
)


def _ensure_dict(container: dict, key: str) -> dict:
    """Return `container[key]` as a dict, coercing it to `{}` first if it is
    missing or holds a non-dict value (e.g. a mangled schema with
    `{"ui": null}` or `{"json": []}`).

    This command is meant to be defensive against malformed schemas, so a
    wrong-typed value is overwritten rather than left to blow up the
    subsequent `.setdefault()` / item-assignment calls with an AttributeError.
    """
    value = container.get(key)
    if not isinstance(value, dict):
        value = {}
        container[key] = value
    return value


def _ensure_list(container: dict, key: str) -> list:
    """Return `container[key]` as a list, coercing it to `[]` first if it is
    missing or holds a non-list value. See `_ensure_dict` for rationale.
    """
    value = container.get(key)
    if not isinstance(value, list):
        value = []
        container[key] = value
    return value


def _last_existing_section(ui_order: list[str], ui_sections: dict) -> str | None:
    """Return the last entry of `ui_order` that is present in `ui_sections`.

    Falls back to the last key of `ui_sections` (insertion order) if none of
    the `ui_order` entries exist in `ui_sections`, or None if there are no
    sections at all.
    """
    for section_name in reversed(ui_order):
        if section_name in ui_sections:
            return section_name
    if ui_sections:
        return next(reversed(ui_sections))
    return None


def _ensure_section_exists(parent: str, ui_sections: dict, ui_order: list[str]) -> bool:
    """Ensure `parent` exists in `ui_sections` and `ui_order`, creating a
    minimal active section (matching the shape of known-good cameratrap
    sections, see cameratrap_rep.json ui.sections["section-2"]) if it is
    missing entirely.

    Returns True if the section was newly created.
    """
    if parent in ui_sections:
        return False
    ui_sections[parent] = {
        "columns": 2,
        "isActive": True,
        "label": "",
        "leftColumn": [],
        "rightColumn": [],
    }
    if parent not in ui_order:
        ui_order.append(parent)
    return True


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Repair broken 'camera trap' event type schemas (both V1 and V2). "
        "Fixes the `tags` field from a deprecated plain-string shape back to the "
        "correct CHOICE_LIST / array shape (V2) or choice-list reference shape (V1), "
        "installs the cameratrap_tags choices, and adds the `tag_count_array` field "
        "if it is missing."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--event-type-value",
            default="cameratrap_rep",
            help="EventType.value to repair (default: cameratrap_rep).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options) -> None:
        event_type_value: str = options["event_type_value"]
        dry_run: bool = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] No changes will be written."))

        # --- Locate the event type(s) -------------------------------------
        event_types = list(EventType.objects.filter(value=event_type_value))
        if not event_types:
            self.stdout.write(
                self.style.NOTICE(f"No EventType with value={event_type_value!r} found for this tenant. Nothing to do.")
            )
            return

        for event_type in event_types:
            if event_type.version == EventType.VersionChoices.VERSION_1:
                self._repair_v1(event_type, dry_run)
            else:
                self._repair_v2(event_type, dry_run)

    # ------------------------------------------------------------------
    # V2 repair
    # ------------------------------------------------------------------

    def _repair_v2(self, event_type: EventType, dry_run: bool) -> None:
        event_type_value = event_type.value

        # --- Parse the schema ---------------------------------------------
        try:
            schema: dict = json.loads(event_type.schema)
        except json.JSONDecodeError as exc:
            self.stderr.write(self.style.ERROR(f"EventType {event_type_value!r} has invalid JSON schema: {exc}"))
            return

        json_schema: dict = _ensure_dict(schema, "json")
        ui_schema: dict = _ensure_dict(schema, "ui")
        json_properties: dict = _ensure_dict(json_schema, "properties")
        ui_fields: dict = _ensure_dict(ui_schema, "fields")
        ui_sections: dict = _ensure_dict(ui_schema, "sections")
        ui_order: list[str] = _ensure_list(ui_schema, "order")

        # --- Independently check what needs repair ------------------------

        # Tags: needs repair when the JSON property is not the array shape OR
        # the UI field is not the CHOICE_LIST shape. This also catches a
        # partially-repaired schema (e.g. JSON already fixed but the UI field
        # is still TEXT/SHORT_TEXT). Note that an intentionally-inactive
        # parent section is NOT part of this check — we only re-activate the
        # section as a side effect of an actual field repair, never on its own.
        current_tags_json = json_properties.get("tags", {})
        tags_needs_repair = (
            current_tags_json.get("type") != "array" or ui_fields.get("tags", {}).get("type") != "CHOICE_LIST"
        )

        # tag_count_array: needs repair when absent from json.properties.
        tag_count_array_needs_repair = "tag_count_array" not in json_properties

        # --- Always check/install choices (even if no schema change) ------
        n_created, n_existing = self._count_choices_delta()

        if not tags_needs_repair and not tag_count_array_needs_repair:
            self.stdout.write(
                self.style.SUCCESS(
                    f"EventType {event_type_value!r} tags and tag_count_array fields are already in the "
                    "correct shape. No schema change needed."
                )
            )
            self.stdout.write(f"Choices: {n_existing} already present, {n_created} would be created.")
            if not dry_run:
                with transaction.atomic():
                    self._install_choices()
                if n_created > 0:
                    cache.delete(f"schema_hash:{event_type_value}")
                    logger.info(
                        "Invalidated schema_hash cache for event type %r (new choices installed)", event_type_value
                    )
                self.stdout.write(self.style.SUCCESS("Choices installation complete (schema was already good)."))
            return

        # --- Compute UI parent for tags -----------------------------------
        existing_tags_ui = ui_fields.get("tags", {})
        existing_parent: str | None = existing_tags_ui.get("parent") if existing_tags_ui else None

        if existing_parent and existing_parent in ui_sections:
            tags_target_parent = existing_parent
        elif FALLBACK_PARENT_SECTION in ui_sections:
            tags_target_parent = FALLBACK_PARENT_SECTION
        else:
            tags_target_parent = _last_existing_section(ui_order, ui_sections) or FALLBACK_PARENT_SECTION

        new_tags_ui_field = {**GOOD_TAGS_UI_FIELD_BASE, "parent": tags_target_parent}
        tags_parent_missing = tags_target_parent not in ui_sections
        tags_section_was_inactive = not tags_parent_missing and not ui_sections[tags_target_parent].get(
            "isActive", True
        )

        # --- Compute UI parent for tag_count_array ------------------------
        # Prefer section-2 if it exists, else fall back like tags does.
        if FALLBACK_PARENT_SECTION in ui_sections:
            tca_target_parent = FALLBACK_PARENT_SECTION
        elif tags_target_parent in ui_sections:
            tca_target_parent = tags_target_parent
        else:
            tca_target_parent = _last_existing_section(ui_order, ui_sections) or FALLBACK_PARENT_SECTION

        new_tag_count_array_ui_field = {**GOOD_TAG_COUNT_ARRAY_UI_FIELD, "parent": tca_target_parent}
        tca_parent_missing = tca_target_parent not in ui_sections
        tca_section_was_inactive = not tca_parent_missing and not ui_sections[tca_target_parent].get("isActive", True)

        # Check if tag_count_array is already referenced in any section column.
        def _is_field_referenced_in_sections(field_name: str) -> bool:
            for section in ui_sections.values():
                for col in ("leftColumn", "rightColumn"):
                    for entry in section.get(col, []):
                        if isinstance(entry, dict) and entry.get("name") == field_name:
                            return True
            return False

        tca_already_in_section = _is_field_referenced_in_sections("tag_count_array")

        # --- Dry-run summary ----------------------------------------------
        if dry_run:
            self.stdout.write("--- Dry-run summary ---")
            self.stdout.write(f"  EventType: {event_type_value!r} (id={event_type.id})")
            if tags_needs_repair:
                self.stdout.write("  Schema fix: YES — tags.json.properties.tags => array/CHOICE_LIST shape")
                self.stdout.write(f"  UI parent preserved as: {tags_target_parent!r}")
                if tags_parent_missing:
                    self.stdout.write(f"  Section {tags_target_parent!r} does not exist; would be created (active)")
                elif tags_section_was_inactive:
                    self.stdout.write(f"  Section {tags_target_parent!r} isActive: false => true")
            else:
                self.stdout.write("  Schema fix: NO — tags already correct")
            if tag_count_array_needs_repair:
                self.stdout.write("  Schema fix: YES — adding tag_count_array (Detections) field")
                self.stdout.write(f"  tag_count_array UI parent: {tca_target_parent!r}")
                if tca_parent_missing:
                    self.stdout.write(f"  Section {tca_target_parent!r} does not exist; would be created (active)")
                elif tca_section_was_inactive:
                    self.stdout.write(f"  Section {tca_target_parent!r} isActive: false => true")
                if not tca_already_in_section:
                    self.stdout.write(f"  Adding tag_count_array reference to {tca_target_parent!r} leftColumn")
            else:
                self.stdout.write("  Schema fix: NO — tag_count_array already present")
            self.stdout.write(f"  Choices to create: {n_created}, already present: {n_existing}")
            self.stdout.write(self.style.WARNING("[DRY RUN] No changes written."))
            return

        # --- Apply mutations inside a transaction -------------------------
        with transaction.atomic():
            if tags_needs_repair:
                # Repair json.properties.tags
                json_properties["tags"] = GOOD_TAGS_JSON_PROPERTY

                # Repair ui.fields.tags
                ui_fields["tags"] = new_tags_ui_field

                # Ensure the tags parent section exists (creating a minimal
                # section if the schema was too mangled to have one) and is
                # visible.
                _ensure_section_exists(tags_target_parent, ui_sections, ui_order)
                ui_sections[tags_target_parent]["isActive"] = True

            if tag_count_array_needs_repair:
                # Add json.properties.tag_count_array
                json_properties["tag_count_array"] = GOOD_TAG_COUNT_ARRAY_JSON_PROPERTY

                # Add ui.fields for tag_count_array, tag, count
                ui_fields["tag_count_array"] = new_tag_count_array_ui_field
                ui_fields["tag"] = GOOD_TAG_UI_FIELD
                ui_fields["count"] = GOOD_COUNT_UI_FIELD

                # Ensure the tca parent section exists (creating a minimal
                # section if necessary) and is visible.
                _ensure_section_exists(tca_target_parent, ui_sections, ui_order)
                ui_sections[tca_target_parent]["isActive"] = True

                # Add a section column reference for tag_count_array if not present.
                if not tca_already_in_section:
                    ui_sections[tca_target_parent].setdefault("leftColumn", []).insert(
                        0, {"type": "field", "name": "tag_count_array"}
                    )

            event_type.schema = json.dumps(schema)
            event_type.save(update_fields=["schema", "updated_at"])

            self._install_choices()

        # Invalidate the schema-hash ETag cache for this event type value.
        # EventType.save() does not do this automatically; the cache key is
        # set by activity.views.response_headers.get_event_type_schema_hash
        # and has a 1-hour TTL.  We delete it so the next request recomputes
        # the hash from the freshly repaired schema.
        cache.delete(f"schema_hash:{event_type_value}")
        logger.info("Invalidated schema_hash cache for event type %r", event_type_value)

        parts: list[str] = []
        if tags_needs_repair:
            parts.append(f"tags schema fixed, ui parent={tags_target_parent!r}")
        if tag_count_array_needs_repair:
            parts.append(f"tag_count_array added, ui parent={tca_target_parent!r}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Repaired EventType {event_type_value!r}: "
                + ", ".join(parts)
                + f", {n_created} choice(s) created, {n_existing} already present."
            )
        )

    # ------------------------------------------------------------------
    # V1 repair
    # ------------------------------------------------------------------

    def _repair_v1(self, event_type: EventType, dry_run: bool) -> None:
        event_type_value = event_type.value

        # --- Parse the schema ---------------------------------------------
        try:
            schema: dict = json.loads(event_type.schema)
        except json.JSONDecodeError as exc:
            self.stderr.write(self.style.ERROR(f"EventType {event_type_value!r} has invalid JSON schema: {exc}"))
            return

        schema_section = schema.get("schema")
        if not isinstance(schema_section, dict) or "properties" not in schema_section:
            self.stderr.write(
                self.style.ERROR(f"EventType {event_type_value!r} (V1) is missing schema.properties; cannot repair.")
            )
            return
        if "definition" not in schema:
            self.stderr.write(
                self.style.ERROR(f"EventType {event_type_value!r} (V1) is missing definition; cannot repair.")
            )
            return

        properties: dict = schema_section["properties"]
        definition: list[dict] = schema["definition"]

        # --- Independently check what needs repair ------------------------

        # Tags: needs repair when not already the choice-list reference shape.
        tags_needs_repair = properties.get("tags") != GOOD_TAGS_V1_SCHEMA_PROPERTY

        # tag_count_array: needs repair when absent from schema.properties.
        tag_count_array_needs_repair = "tag_count_array" not in properties

        # --- Always check/install choices (even if no schema change) ------
        n_created, n_existing = self._count_choices_delta()

        if not tags_needs_repair and not tag_count_array_needs_repair:
            self.stdout.write(
                self.style.SUCCESS(
                    f"EventType {event_type_value!r} (V1) tags and tag_count_array fields are already in "
                    "the correct shape. No schema change needed."
                )
            )
            self.stdout.write(f"Choices: {n_existing} already present, {n_created} would be created.")
            if not dry_run:
                with transaction.atomic():
                    self._install_choices()
                if n_created > 0:
                    cache.delete(f"schema_hash:{event_type_value}")
                    logger.info(
                        "Invalidated schema_hash cache for event type %r (new choices installed)", event_type_value
                    )
                self.stdout.write(self.style.SUCCESS("Choices installation complete (schema was already good)."))
            return

        has_tags_definition = any(entry.get("key") == "tags" for entry in definition)
        has_tca_definition = any(entry.get("key") == "tag_count_array" for entry in definition)

        # --- Dry-run summary ----------------------------------------------
        if dry_run:
            self.stdout.write("--- Dry-run summary (V1) ---")
            self.stdout.write(f"  EventType: {event_type_value!r} (id={event_type.id})")
            if tags_needs_repair:
                self.stdout.write("  Schema fix: YES — schema.properties.tags => choice-list reference shape")
                if not has_tags_definition:
                    self.stdout.write("  Definition fix: YES — appending tags definition entry")
            else:
                self.stdout.write("  Schema fix: NO — tags already correct")
            if tag_count_array_needs_repair:
                self.stdout.write("  Schema fix: YES — adding tag_count_array (Detections) property")
                if not has_tca_definition:
                    self.stdout.write("  Definition fix: YES — appending tag_count_array definition entry")
            else:
                self.stdout.write("  Schema fix: NO — tag_count_array already present")
            self.stdout.write(f"  Choices to create: {n_created}, already present: {n_existing}")
            self.stdout.write(self.style.WARNING("[DRY RUN] No changes written."))
            return

        # --- Apply mutations inside a transaction -------------------------
        with transaction.atomic():
            if tags_needs_repair:
                properties["tags"] = GOOD_TAGS_V1_SCHEMA_PROPERTY
                if not has_tags_definition:
                    definition.append(GOOD_TAGS_V1_DEFINITION_ENTRY)

            if tag_count_array_needs_repair:
                properties["tag_count_array"] = GOOD_TAG_COUNT_ARRAY_V1_SCHEMA_PROPERTY
                if not has_tca_definition:
                    definition.append(GOOD_TAG_COUNT_ARRAY_V1_DEFINITION_ENTRY)

            schema["schema"]["properties"] = properties
            schema["definition"] = definition

            event_type.schema = json.dumps(schema)
            event_type.save(update_fields=["schema", "updated_at"])

            self._install_choices()

        # Invalidate the schema-hash ETag cache for this event type value.
        cache.delete(f"schema_hash:{event_type_value}")
        logger.info("Invalidated schema_hash cache for event type %r", event_type_value)

        parts: list[str] = []
        if tags_needs_repair:
            parts.append("tags schema fixed")
        if tag_count_array_needs_repair:
            parts.append("tag_count_array added")
        self.stdout.write(
            self.style.SUCCESS(
                f"Repaired EventType {event_type_value!r} (V1): "
                + ", ".join(parts)
                + f", {n_created} choice(s) created, {n_existing} already present."
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_choices_fixture(self) -> list[dict]:
        """Load and return the choices fixture entries."""
        with _CHOICES_FIXTURE_PATH.open() as fh:
            return json.load(fh)

    def _count_choices_delta(self) -> tuple[int, int]:
        """Return (would_create, already_exists) counts without writing.

        Runs a single bulk query for all (model, field) pairs referenced by
        the fixture rather than one `.exists()` query per fixture entry.
        """
        entries = self._load_choices_fixture()
        model_field_pairs = {(entry["fields"]["model"], entry["fields"]["field"]) for entry in entries}

        existing_keys: set[tuple[str, str, str]] = set()
        if model_field_pairs:
            query = Q()
            for model, field in model_field_pairs:
                query |= Q(model=model, field=field)
            existing_keys = set(Choice.objects.filter(query).values_list("model", "field", "value"))

        n_created = 0
        n_existing = 0
        for entry in entries:
            fields = entry["fields"]
            key = (fields["model"], fields["field"], fields["value"])
            if key in existing_keys:
                n_existing += 1
            else:
                n_created += 1
        return n_created, n_existing

    def _install_choices(self) -> None:
        """Upsert all choices from the fixture into the current tenant.

        Deliberately ignores fixture pk values so that each tenant gets its own
        UUID primary keys — reusing fixture pks across tenants would clobber
        another tenant's rows.
        """
        entries = self._load_choices_fixture()
        for entry in entries:
            fields = entry["fields"]
            Choice.objects.update_or_create(
                model=fields["model"],
                field=fields["field"],
                value=fields["value"],
                defaults={
                    "display": fields.get("display", ""),
                    "is_active": fields.get("is_active", True),
                    "ordernum": fields.get("ordernum"),
                },
            )
