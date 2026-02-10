from django.db import migrations

RENAME_PERMISSIONS_SQL = """
UPDATE auth_permission
SET name = REPLACE(name, 'Feature Class', 'Feature Type')
WHERE codename IN (
    'add_spatialfeaturetype',
    'change_spatialfeaturetype',
    'delete_spatialfeaturetype',
    'view_spatialfeaturetype'
) AND name LIKE '%%Feature Class%%';
"""

REVERSE_PERMISSIONS_SQL = """
UPDATE auth_permission
SET name = REPLACE(name, 'Feature Type', 'Feature Class')
WHERE codename IN (
    'add_spatialfeaturetype',
    'change_spatialfeaturetype',
    'delete_spatialfeaturetype',
    'view_spatialfeaturetype'
) AND name LIKE '%%Feature Type%%';
"""


class Migration(migrations.Migration):

    dependencies = [
        ("mapping", "0075_alter_spatialfeaturetype_options"),
    ]

    operations = [
        migrations.RunSQL(
            sql=RENAME_PERMISSIONS_SQL,
            reverse_sql=REVERSE_PERMISSIONS_SQL,
        ),
    ]
