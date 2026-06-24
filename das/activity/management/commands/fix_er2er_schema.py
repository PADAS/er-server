"""Repair the er2er provenance fields on V2 event-type schemas.

The er2er integration (cdip-integrations) copies events from a source ER tenant
into a destination tenant and stamps four provenance fields into every event's
``event_details``:

    er2er_src_id              (string)  - source event UUID
    er2er_src_system          (string)  - source system value
    er2er_src_serial_number   (number)  - source event serial number
    er2er_src_service_root    (string)  - source service root

In ER Schema V2 every ``event_details`` key must be declared in
``schema.json.properties`` (the schema root sets ``unevaluatedProperties: false``),
and a field is hidden from the report form by living in a ``schema.ui.sections``
section whose ``isActive`` is ``False``. A destination event type can end up
misconfigured when:

* the provenance fields were never added (e.g. the source was still V1 and the
  old V1 PATCH 404'd against a destination already migrated to V2),
* ``er2er_src_serial_number`` was declared ``string`` instead of ``number``
  (the value stored is numeric, and the V2 meta-schema requires numeric fields
  to be ``"type": {"const": "number"}``), or
* the hidden ``ui`` section / ``ui.fields`` entries are missing, so the fields
  are declared but not actually hidden.

This command brings the schema of one or more V2 event types into the canonical
shape produced by ``er2er_syncher.add_er2er_fields_to_v2_schema``. The injection
logic below is intentionally a copy of that function and must stay in sync with
it.

Usage:
    # Fix specific event type(s) in a tenant
    python manage.py fix_er2er_schema sgrc_carcass_rep sgrc_contact_rep --tenant_domain <domain>

    # Preview without writing
    python manage.py fix_er2er_schema sgrc_carcass_rep --tenant_domain <domain> --dry-run

    # Fix every V2 event type in the tenant that already carries any er2er field
    python manage.py fix_er2er_schema --all --tenant_domain <domain>

Note: an event type missing *all four* provenance fields cannot be auto-detected
by ``--all`` (nothing marks it as an er2er destination), so pass its value
explicitly in that case.
"""

import copy
import json

from django.core.management.base import BaseCommand, CommandError

from activity.models import EventType
from utils.tenant.commands import TenantCommandMixin

# Canonical er2er provenance fields: key -> {"type", "title"}. Keep in sync with
# ER2ER_SRC_FIELDS in cdip-integrations/er2er/er2er_syncher.py.
ER2ER_SRC_FIELDS = {
    "er2er_src_id": {"type": "string", "title": "ID of Source Event"},
    "er2er_src_system": {"type": "string", "title": "Name of Source ER System"},
    "er2er_src_serial_number": {"type": "number", "title": "Serial Number of Source Event"},
    "er2er_src_service_root": {"type": "string", "title": "Service Root of Source Event"},
}

# Hidden (isActive: False) ui section the provenance fields live in.
ER2ER_HIDDEN_SECTION_ID = "section-er2er-hidden"


def _ui_field_for(field):
    """The ui.fields entry for a provenance field, by JSON type."""
    if field["type"] == "number":
        return {"type": "NUMERIC", "placeholder": "", "parent": ER2ER_HIDDEN_SECTION_ID}
    return {"type": "TEXT", "inputType": "SHORT_TEXT", "placeholder": "", "parent": ER2ER_HIDDEN_SECTION_ID}


def apply_er2er_v2_schema(schema):
    """Mutate a V2 schema dict (``{"json": ..., "ui": ...}``) so the er2er
    provenance fields are declared and hidden. Idempotent.

    Mirror of ``er2er_syncher.add_er2er_fields_to_v2_schema``.
    """
    json_schema = schema.setdefault("json", {})
    properties = json_schema.setdefault("properties", {})
    ui = schema.setdefault("ui", {})
    ui_fields = ui.setdefault("fields", {})
    ui_sections = ui.setdefault("sections", {})
    ui_order = ui.setdefault("order", [])

    section = ui_sections.setdefault(
        ER2ER_HIDDEN_SECTION_ID,
        {
            "columns": 1,
            "isActive": False,
            "label": "",
            "leftColumn": [],
            "rightColumn": [],
            "conditions": [],
        },
    )
    section["isActive"] = False  # enforce hidden even if the section pre-existed
    if ER2ER_HIDDEN_SECTION_ID not in ui_order:
        ui_order.append(ER2ER_HIDDEN_SECTION_ID)
    fields_in_section = {entry.get("name") for entry in section.get("leftColumn", [])}

    for key, field in ER2ER_SRC_FIELDS.items():
        # Active provenance fields, not legacy ones: deprecated=False. Hiding is
        # done by the isActive=False section above, not this flag.
        properties[key] = {
            "type": field["type"],
            "title": field["title"],
            "description": "",
            "deprecated": False,
        }
        ui_fields[key] = _ui_field_for(field)
        if key not in fields_in_section:
            section["leftColumn"].append({"type": "field", "name": key})
            fields_in_section.add(key)
    return schema


def diagnose(schema):
    """Return a list of human-readable problems with a V2 schema's er2er fields.

    Empty list means the schema already matches the canonical shape.
    """
    issues = []
    properties = (schema.get("json") or {}).get("properties") or {}
    ui = schema.get("ui") or {}
    ui_fields = ui.get("fields") or {}
    ui_sections = ui.get("sections") or {}
    ui_order = ui.get("order") or []

    section = ui_sections.get(ER2ER_HIDDEN_SECTION_ID)
    section_fields = {e.get("name") for e in section.get("leftColumn", [])} if section else set()

    for key, field in ER2ER_SRC_FIELDS.items():
        prop = properties.get(key)
        if prop is None:
            issues.append(f"json.properties['{key}'] missing")
        elif prop.get("type") != field["type"]:
            issues.append(f"json.properties['{key}'].type is {prop.get('type')!r}, expected {field['type']!r}")
        if key not in ui_fields:
            issues.append(f"ui.fields['{key}'] missing")
        if key not in section_fields:
            issues.append(f"'{key}' not in hidden ui section")

    if section is None:
        issues.append(f"ui.sections['{ER2ER_HIDDEN_SECTION_ID}'] missing")
    elif section.get("isActive") is not False:
        issues.append(
            f"ui.sections['{ER2ER_HIDDEN_SECTION_ID}'].isActive is {section.get('isActive')!r}, expected False"
        )
    if ER2ER_HIDDEN_SECTION_ID not in ui_order:
        issues.append(f"'{ER2ER_HIDDEN_SECTION_ID}' not in ui.order")
    return issues


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Repair the er2er provenance fields (er2er_src_*) on V2 event-type schemas: "
        "add missing fields, fix er2er_src_serial_number's type, and ensure the hidden ui "
        "section is present. Scoped to the tenant given by --tenant_domain."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "values",
            nargs="*",
            help="Event type value(s) to fix. Omit only when using --all.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="fix_all",
            help=(
                "Fix every V2 event type in the tenant that already carries at least one "
                "er2er_src_* property. A type missing all four fields must be named explicitly."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        values = options["values"]
        fix_all = options["fix_all"]
        dry_run = options["dry_run"]
        verbosity = options.get("verbosity", 1)

        if not values and not fix_all:
            raise CommandError("Specify one or more event type values, or pass --all.")
        if values and fix_all:
            raise CommandError("Pass either explicit event type values or --all, not both.")

        qs = EventType.objects.filter(version=EventType.VersionChoices.VERSION_2)
        if values:
            qs = qs.filter(value__in=values)

        candidates = []  # list of (event_type, parsed_schema)
        for et in qs:
            try:
                schema = json.loads(et.schema) if et.schema else {}
            except (TypeError, ValueError) as e:
                self.stderr.write(f"  ! {et.value}: could not parse schema ({e}); skipping")
                continue
            if "json" not in schema:
                self.stderr.write(f"  ! {et.value}: not a V2-shaped schema (no 'json' key); skipping")
                continue
            if fix_all:
                props = (schema.get("json") or {}).get("properties") or {}
                if not any(key in props for key in ER2ER_SRC_FIELDS):
                    continue
            candidates.append((et, schema))

        if values:
            found = {et.value for et, _ in candidates}
            for missing in sorted(set(values) - found):
                self.stderr.write(f"  ! no V2 event type found with value '{missing}'")

        fixed = already_ok = 0
        for et, schema in candidates:
            desired = apply_er2er_v2_schema(copy.deepcopy(schema))
            if desired == schema:
                already_ok += 1
                if verbosity >= 2:
                    self.stdout.write(f"  = {et.value} ({et.id}): already correct")
                continue

            issues = diagnose(schema) or ["schema differs from the canonical er2er hidden-field shape"]
            self.stdout.write(f"  * {et.value} ({et.id}): {len(issues)} issue(s)")
            for issue in issues:
                self.stdout.write(f"      - {issue}")

            if dry_run:
                self.stdout.write("      -> would fix (dry-run)")
            else:
                et.schema = json.dumps(desired, indent=2)
                et.save()
                self.stdout.write("      -> fixed")
            fixed += 1

        verb = "Would fix" if dry_run else "Fixed"
        self.stdout.write(self.style.SUCCESS(f"Done. {verb} {fixed} event type(s); {already_ok} already correct."))
