import os
from functools import partial

from django.db import migrations

from utils.models import create_all_permissions
from utils.permission_sets import create_permissionset_csv, set_permissions_set_hash

current_file = os.path.basename(__file__)
create_csv = partial(create_permissionset_csv, migration_filename=current_file)


def catchup_create_permissions(apps, schema_editor):
    create_all_permissions()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_recreate_fks_content_types"),
    ]

    operations = [
        migrations.RunPython(
            set_permissions_set_hash,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            catchup_create_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            create_csv,
            migrations.RunPython.noop,
        ),
    ]
