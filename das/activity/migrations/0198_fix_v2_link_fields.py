import json

from django.db import migrations

from utils.tenant.managers import UnsetDASTenantContextManager


def normalize_v2_link_fields(schema: dict) -> tuple[dict, bool]:
    ui_fields = schema.get("ui", {}).get("fields")
    if not isinstance(ui_fields, dict):
        return schema, False

    changed = False

    for field_name, ui_field in ui_fields.items():
        if not isinstance(ui_field, dict) or ui_field.get("type") != "LINK":
            continue

        ui_field["type"] = "TEXT"
        ui_field["inputType"] = "SHORT_TEXT"
        ui_field.setdefault("placeholder", "")

        json_schema = schema.get("json", {})

        field_schema = json_schema.get("properties", {}).get(field_name)
        if isinstance(field_schema, dict) and field_schema.get("type") == "string":
            field_schema["format"] = "uri"
            changed = True

    return schema, changed


def fix_v2_schemas(apps, schema_editor):
    with UnsetDASTenantContextManager():
        EventType = apps.get_model("activity", "EventType")
        db_alias = schema_editor.connection.alias

        queryset = EventType.objects.using(db_alias).filter(version="2")

        for event_type in queryset:
            if not event_type.schema:
                continue

            try:
                schema = json.loads(event_type.schema)
                if not isinstance(schema, dict):
                    continue
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                continue

            normalized_schema, changed = normalize_v2_link_fields(schema)
            if not changed:
                continue

            event_type.schema = json.dumps(normalized_schema, indent=2)
            event_type.save(using=db_alias, update_fields=["schema", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("activity", "0197_update_geofence_schema"),
    ]

    operations = [
        migrations.RunPython(fix_v2_schemas, migrations.RunPython.noop),
    ]
