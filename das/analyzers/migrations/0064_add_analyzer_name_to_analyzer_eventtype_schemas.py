import json
import logging
import re

from schema_migration_tool import preprocess_template_vars

from django.apps import apps
from django.db import migrations

from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import TenantContextManager, UnsetDASTenantContextManager

logger = logging.getLogger(__name__)


# Inverse of schema_migration_tool.preprocess_template_vars: strip the
# surrounding quotes that the preprocessor adds so the saved schema retains
# bare {{...}} Django template tokens. The runtime schema renderer parses
# unquoted tokens, so we must round-trip them back to that form.
_QUOTED_TEMPLATE_VAR_RE = re.compile(r'"(\{\{(?:enum|query|table)___[^}]+___(?:values|names|map)\}\})"')


def _restore_template_vars(schema_str: str) -> str:
    return _QUOTED_TEMPLATE_VAR_RE.sub(r"\1", schema_str)


# Event type values produced by the analyzers updated in PR #3870 (ERA-13151)
# which now populate event_details["analyzer_name"] at runtime. Existing
# EventType rows need their stored schemas patched to expose the new field.
ANALYZER_EVENT_TYPE_VALUES = (
    "environmental_value",
    "environmental_all_clear",
    "geofence_break",
    "immobility",
    "immobility_all_clear",
    "low_speed_percentile",
    "low_speed_percentile_all_clear",
    "low_speed_wilcoxon",
    "low_speed_wilcoxon_all_clear",
    "movement_cluster",
    "observation_attribute",
    "proximity",
    "subject_proximity",
)

ANALYZER_NAME_PROPERTY_V1 = {"type": "string", "title": "Analyzer Name"}

ANALYZER_NAME_PROPERTY_V2 = {
    "deprecated": False,
    "title": "Analyzer Name",
    "default": "",
    "description": "",
    "type": "string",
}


def _build_analyzer_name_ui_field_v2(parent_section: str) -> dict:
    return {
        "conditionalDependents": [],
        "parent": parent_section,
        "type": "TEXT",
        "inputType": "SHORT_TEXT",
        "placeholder": "",
    }


def _inject_v1(schema: dict) -> bool:
    inner = schema.get("schema")
    if not isinstance(inner, dict):
        return False
    properties = inner.get("properties")
    if not isinstance(properties, dict) or "analyzer_name" in properties:
        return False

    inner["properties"] = {"analyzer_name": ANALYZER_NAME_PROPERTY_V1, **properties}

    # "definition" can live either inside "schema" (legacy) or at the top level.
    if "definition" in inner:
        container, key = inner, "definition"
    elif "definition" in schema:
        container, key = schema, "definition"
    else:
        return True

    definition = container.get(key)
    if not isinstance(definition, list):
        return True

    if definition and isinstance(definition[0], dict) and isinstance(definition[0].get("items"), list):
        first_items = definition[0]["items"]
        if "analyzer_name" not in first_items:
            definition[0]["items"] = ["analyzer_name", *first_items]
    elif "analyzer_name" not in definition:
        container[key] = ["analyzer_name", *definition]

    return True


def _inject_v2(schema: dict) -> bool:
    json_section = schema.get("json")
    if not isinstance(json_section, dict):
        return False
    properties = json_section.get("properties")
    if not isinstance(properties, dict) or "analyzer_name" in properties:
        return False

    json_section["properties"] = {"analyzer_name": ANALYZER_NAME_PROPERTY_V2, **properties}

    ui = schema.get("ui")
    if not isinstance(ui, dict):
        return True

    # Pick the section to host analyzer_name. "section-2" matches the new-tenant
    # default for movement_cluster; otherwise fall back to the first section in
    # the schema's declared order (this is what the V1→V2 migrator produces —
    # `section-1`, `section-2`, ...).
    sections = ui.get("sections")
    parent_section = "section-2"
    if isinstance(sections, dict):
        if "section-2" not in sections:
            order = ui.get("order")
            if isinstance(order, list) and order:
                parent_section = order[0]
            else:
                parent_section = next(iter(sections), parent_section)

    ui_fields = ui.get("fields")
    if isinstance(ui_fields, dict) and "analyzer_name" not in ui_fields:
        ui["fields"] = {
            "analyzer_name": _build_analyzer_name_ui_field_v2(parent_section),
            **ui_fields,
        }

    if isinstance(sections, dict):
        section = sections.get(parent_section)
        if isinstance(section, dict):
            left = section.get("leftColumn")
            if isinstance(left, list) and not any(
                isinstance(item, dict) and item.get("name") == "analyzer_name" for item in left
            ):
                section["leftColumn"] = [{"name": "analyzer_name", "type": "field"}, *left]

    return True


VERSION_2 = "2"


def add_analyzer_name_to_schema(schema: dict, version: str) -> bool:
    """Mutate ``schema`` in place. Return True if any change was made.

    The EventType.version column is authoritative for picking the schema shape:
    a tenant who has run the V1→V2 migration tool will have version="2" even
    though the analyzer source code still emits a V1 schema by default.
    """
    if version == VERSION_2:
        return _inject_v2(schema)
    return _inject_v1(schema)


def _patch_eventtypes_for_current_tenant(EventType, db_alias: str, domain: str) -> None:
    queryset = EventType.objects.using(db_alias).filter(value__in=ANALYZER_EVENT_TYPE_VALUES)
    for event_type in queryset.iterator():
        if not event_type.schema:
            continue
        # V1 schemas can contain Django template tokens (e.g. `{{enum___x___values}}`)
        # that the runtime renderer expands at request time. preprocess_template_vars
        # wraps those tokens in quotes so the string is parseable JSON; we undo the
        # wrapping on the way out so the persisted schema keeps its templates.
        try:
            parsed = json.loads(preprocess_template_vars(event_type.schema))
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "Skipping EventType id=%s value=%s in tenant %s: schema is not valid JSON",
                event_type.id,
                event_type.value,
                domain,
            )
            continue
        if not isinstance(parsed, dict):
            continue

        if add_analyzer_name_to_schema(parsed, event_type.version):
            event_type.schema = _restore_template_vars(json.dumps(parsed, indent=2))
            event_type.save(using=db_alias, update_fields=["schema", "updated_at"])


def forward(_, schema_editor):
    DASTenant = apps.get_model("core", "DASTenant")
    EventType = apps.get_model("activity", "EventType")
    db_alias = schema_editor.connection.alias

    with UnsetDASTenantContextManager():
        all_tenants = list(DASTenant.objects.using(db_alias).all())

    for tenant in all_tenants:
        domain = tenant.domain
        logger.debug("Patching analyzer EventType schemas for tenant %s", domain)
        try:
            with TenantContextManager(domain=domain):
                _patch_eventtypes_for_current_tenant(EventType, db_alias, domain)
        except (DASTenant.DoesNotExist, TenantNotFoundException):
            logger.warning(
                "DASTenant with domain %s does not exist in TMS, skipping analyzer EventType schema patch",
                domain,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("analyzers", "0063_movementclusteranalyzerconfig_min_subjects_in_cluster"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
