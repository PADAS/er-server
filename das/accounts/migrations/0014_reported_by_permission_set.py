from django.db import migrations

import utils.models


def create_reported_by_permission_set(apps, schema_editor):
    utils.models.migrate_permissions(apps)

    db_alias = schema_editor.connection.alias
    PermissionSet = apps.get_model(app_label="accounts", model_name="PermissionSet")

    PermissionSet.objects.using(db_alias).bulk_create(
        [
            PermissionSet(
                **{
                    "pk": "b5057387-9f6c-4685-8ec1-46ad29684eea",
                    "created_at": "2017-06-01T1:00:00.000000+00:00",
                    "updated_at": "2017-06-01T1:00:00.000000+00:00",
                    "name": "Reported By Users",
                }
            )
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_profiles"),
    ]

    operations = [
        migrations.RunPython(create_reported_by_permission_set),
    ]
