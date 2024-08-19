from django.db import migrations

from utils.models import create_all_permissions


def catchup_create_permissions(apps, schema_editor):
    create_all_permissions()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_recreate_fks_content_types"),
    ]

    operations = [
        migrations.RunPython(
            catchup_create_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
