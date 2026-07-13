"""Change the field type of a single property in a V2 EventType schema.

First supported conversion: ``string`` -> ``number`` (a plain TEXT field
becomes a NUMERIC field).

This command only rewrites the ``EventType.schema``. It does not touch any
``EventDetails`` rows already stored against events of this type — run the
existing ``fix_event_details`` command separately (with ``--transform
coerce-type --to-type number``) to coerce stored values to match. On
``--apply`` this command prints the suggested follow-up invocation.

Validation is two-part: the transformed property/field is checked strictly
against ``numeric_field_json_schema`` / ``numeric_field_ui_schema``, and the
whole schema is checked for *regressions* only — i.e. new validation errors
introduced by the transform — rather than requiring the whole schema to be
perfectly conformant. Real-world V2 schemas often carry pre-existing,
unrelated nonconformities (e.g. extra keys on other fields); those are left
untouched and reported as warnings rather than blocking the command.

Usage examples
--------------
    # Preview the conversion without writing
    python manage.py change_event_type_property_type \\
        --event-type wildlife_sighting --property number_of_cars --to-type number \\
        --tenant_domain <domain>

    # Apply the conversion
    python manage.py change_event_type_property_type \\
        --event-type wildlife_sighting --property number_of_cars --to-type number \\
        --tenant_domain <domain> --apply
"""

from __future__ import annotations

import json
import logging
from enum import Enum

from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema.validators import Draft202012Validator

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from activity.models import EventType
from activity.schemas.eventtype_meta_schemas import (
    main_event_type_schema,
    numeric_field_json_schema,
    numeric_field_ui_schema,
)
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class ToType(str, Enum):
    NUMBER = "number"


# JSON-side property keys carried over verbatim from the source text property,
# if present, onto the new numeric property.
_JSON_CARRY_OVER_KEYS = ("deprecated", "title", "description")

# UI-side property keys carried over verbatim from the source TEXT ui field,
# if present, onto the new NUMERIC ui field.
_UI_CARRY_OVER_KEYS = ("parent", "conditionalDependents", "placeholder")


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Change the field type of a single property in a V2 EventType schema. "
        "Dry-runs by default — pass --apply to write changes."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--event-type",
            dest="event_type",
            required=True,
            metavar="VALUE",
            help="The EventType value to modify.",
        )
        parser.add_argument(
            "--property",
            dest="property_key",
            required=True,
            metavar="KEY",
            help="The property key inside json.properties to modify.",
        )
        parser.add_argument(
            "--to-type",
            dest="to_type",
            required=True,
            choices=[t.value for t in ToType],
            help="Target field type.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes to the database. Without this flag the command is a dry run.",
        )

    def handle(self, *args, **options) -> None:
        event_type_value: str = options["event_type"]
        property_key: str = options["property_key"]
        to_type = ToType(options["to_type"])
        apply: bool = options["apply"]

        event_type = self._get_v2_event_type(event_type_value)
        json_properties, ui_fields = self._parse_schema(event_type)

        if property_key not in json_properties:
            raise CommandError(
                f"Property '{property_key}' not found in json.properties of event type '{event_type_value}'."
            )

        json_property = json_properties[property_key]
        ui_field = ui_fields.get(property_key)

        if to_type is ToType.NUMBER:
            if self._is_already_converted(json_property, ui_field):
                self.stdout.write(self.style.SUCCESS(f"Property '{property_key}' is already converted. No changes."))
                return

            ui_field = self._check_string_to_number_eligible(property_key, json_property, ui_field)
            new_json_property = self._transform_json_string_to_number(json_property)
            new_ui_field = self._transform_ui_text_to_numeric(ui_field)
        else:  # pragma: no cover — only one ToType member exists today
            raise CommandError(f"Unsupported --to-type: {to_type.value}")

        self.stdout.write(self.style.NOTICE(f"\n  json.properties.{property_key}"))
        self.stdout.write(f"    before : {json.dumps(json_property)}")
        self.stdout.write(f"    after  : {json.dumps(new_json_property)}")
        self.stdout.write(self.style.NOTICE(f"\n  ui.fields.{property_key}"))
        self.stdout.write(f"    before : {json.dumps(ui_field)}")
        self.stdout.write(f"    after  : {json.dumps(new_ui_field)}")

        self._validate_transformed_property(new_json_property, new_ui_field)

        original_schema = json.loads(event_type.schema)
        parsed_schema = json.loads(event_type.schema)
        parsed_schema["json"]["properties"][property_key] = new_json_property
        parsed_schema["ui"]["fields"][property_key] = new_ui_field

        self._check_whole_schema_for_regressions(original_schema, parsed_schema)

        if not apply:
            self.stdout.write(self.style.WARNING("\n  Dry run — no changes written. Pass --apply to persist."))
            return

        new_schema_text = json.dumps(parsed_schema, indent=2)

        try:
            event_type.schema = new_schema_text
            event_type.updated_at = timezone.now()
            event_type.save(update_fields=["schema", "updated_at"])
        except ValidationError as exc:
            raise CommandError(f"EventType failed model validation on save: {'; '.join(exc.messages)}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Updated property '{property_key}' on event type '{event_type_value}' to type '{to_type.value}'."
            )
        )

        domain = event_type.das_tenant.domain
        self.stdout.write(
            self.style.NOTICE(
                "\n  Suggested follow-up to coerce existing EventDetails values:\n"
                f"    python manage.py fix_event_details --tenant_domain {domain} "
                f"--event-type {event_type_value} --property {property_key} "
                "--transform coerce-type --to-type number --apply\n"
                "  Note: string values that cannot be parsed as numbers (including empty strings) "
                "will be skipped with warnings by that command and may need alternate handling."
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_v2_event_type(event_type_value: str) -> EventType:
        try:
            event_type = EventType.objects.get(value=event_type_value)
        except EventType.DoesNotExist:
            raise CommandError(f"No event type found with value '{event_type_value}'.")

        if event_type.version != EventType.VersionChoices.VERSION_2:
            raise CommandError(f"Event type '{event_type_value}' is not a V2 event type. This command is V2-only.")

        return event_type

    @staticmethod
    def _parse_schema(event_type: EventType) -> tuple[dict, dict]:
        try:
            parsed = json.loads(event_type.schema)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Event type '{event_type.value}' has invalid JSON schema text: {exc}")

        json_schema = parsed.get("json")
        if not isinstance(json_schema, dict):
            raise CommandError(f"Event type '{event_type.value}' schema is missing a 'json' object.")

        json_properties = json_schema.get("properties")
        if not isinstance(json_properties, dict):
            raise CommandError(f"Event type '{event_type.value}' schema is missing 'json.properties'.")

        ui_schema = parsed.get("ui")
        if not isinstance(ui_schema, dict):
            raise CommandError(f"Event type '{event_type.value}' schema is missing a 'ui' object.")

        ui_fields = ui_schema.get("fields")
        if not isinstance(ui_fields, dict):
            raise CommandError(f"Event type '{event_type.value}' schema is missing 'ui.fields'.")

        return json_properties, ui_fields

    @staticmethod
    def _is_already_converted(json_property: dict, ui_field: dict | None) -> bool:
        return json_property.get("type") == "number" and ui_field is not None and ui_field.get("type") == "NUMERIC"

    @staticmethod
    def _check_string_to_number_eligible(property_key: str, json_property: dict, ui_field: dict | None) -> dict:
        if json_property.get("type") == "array":
            raise CommandError(f"Property '{property_key}' is an array/multi-choice field; cannot convert to number.")

        if json_property.get("type") != "string":
            raise CommandError(
                f"Property '{property_key}' has type '{json_property.get('type')}', not 'string'; "
                "cannot convert to number."
            )

        if "anyOf" in json_property or "$ref" in json_property:
            raise CommandError(f"Property '{property_key}' is a choice-list field; cannot convert to number.")

        if "format" in json_property:
            raise CommandError(f"Property '{property_key}' has a 'format' constraint; cannot convert to number.")

        if "enum" in json_property:
            raise CommandError(f"Property '{property_key}' has an 'enum' constraint; cannot convert to number.")

        if ui_field is None:
            raise CommandError(f"Property '{property_key}' has no corresponding ui.fields entry.")

        if ui_field.get("type") != "TEXT":
            raise CommandError(
                f"Property '{property_key}' has ui field type '{ui_field.get('type')}', not 'TEXT'; "
                "cannot convert to number."
            )

        return ui_field

    @staticmethod
    def _transform_json_string_to_number(json_property: dict) -> dict:
        new_property = {key: json_property[key] for key in _JSON_CARRY_OVER_KEYS if key in json_property}
        new_property["type"] = "number"

        if "default" in json_property:
            coerced_default = Command._coerce_default_to_number(json_property["default"])
            if coerced_default is not None:
                new_property["default"] = coerced_default

        return new_property

    @staticmethod
    def _coerce_default_to_number(default: object) -> int | float | None:
        if isinstance(default, bool):
            return None
        if isinstance(default, (int, float)):
            return default
        if not isinstance(default, str) or default == "":
            return None
        try:
            return int(default)
        except (TypeError, ValueError):
            pass
        try:
            return float(default)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _transform_ui_text_to_numeric(ui_field: dict) -> dict:
        new_field = {key: ui_field[key] for key in _UI_CARRY_OVER_KEYS if key in ui_field}
        new_field["type"] = "NUMERIC"
        return new_field

    @staticmethod
    def _validate_transformed_property(new_json_property: dict, new_ui_field: dict) -> None:
        """Strictly validate only the property/field this command just transformed."""
        for label, instance, schema in (
            ("json property", new_json_property, numeric_field_json_schema),
            ("ui field", new_ui_field, numeric_field_ui_schema),
        ):
            try:
                Draft202012Validator(schema).validate(instance)
            except JSONSchemaValidationError as exc:
                raise CommandError(f"Transformed {label} failed strict validation: {exc.message}")

    @staticmethod
    def _schema_error_keys(schema: dict) -> dict[tuple[tuple[str, ...], str], JSONSchemaValidationError]:
        """Map each whole-schema validation error to a stable (path, message) key."""
        validator = Draft202012Validator(main_event_type_schema)
        errors: dict[tuple[tuple[str, ...], str], JSONSchemaValidationError] = {}
        for err in validator.iter_errors(schema):
            path = tuple(str(part) for part in err.absolute_path)
            errors[(path, err.message)] = err
        return errors

    def _check_whole_schema_for_regressions(self, original_schema: dict, transformed_schema: dict) -> None:
        """Refuse only on validation errors introduced by the transform.

        Real-world V2 schemas often carry pre-existing nonconformities that
        are unrelated to the property being changed (e.g. extra keys on
        other fields). Requiring the whole schema to be perfectly
        conformant would make this command unusable on such schemas, so
        only *new* errors — introduced by this transform — block the
        write. Pre-existing errors are reported as warnings and left as-is.
        """
        original_errors = self._schema_error_keys(original_schema)
        transformed_errors = self._schema_error_keys(transformed_schema)

        new_keys = [key for key in transformed_errors if key not in original_errors]
        if new_keys:
            details = "; ".join(f"{'.'.join(path) or '<root>'}: {message}" for path, message in new_keys)
            raise CommandError(f"Transformed schema introduced new validation error(s): {details}")

        pre_existing_keys = [key for key in transformed_errors if key in original_errors]
        if pre_existing_keys:
            paths = sorted({".".join(path) or "<root>" for path, _ in pre_existing_keys})
            message = (
                f"{len(pre_existing_keys)} pre-existing schema validation issue(s) unrelated to this "
                f"change were found and left as-is: {', '.join(paths)}"
            )
            logger.warning(message)
            self.stdout.write(self.style.WARNING(f"\n  {message}"))
