import os
from functools import partial

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count

from utils.json import load_from_file
from utils.permission_sets import create_permissionset_csv, set_permissions_set_hash

current_file = os.path.basename(__file__)
create_csv = partial(create_permissionset_csv, migration_filename=current_file)

SQL = """
DO
$$
    DECLARE
        ROW     RECORD;
        NEW_ID  INTEGER;
        BASE_ID INTEGER;
    BEGIN
        SELECT NEXTVAL('auth_permission_id_seq') INTO BASE_ID;
        BASE_ID = BASE_ID + 10000;
        -- DROP FK
        ALTER TABLE auth_group_permissions
            DROP CONSTRAINT IF EXISTS auth_group_permissio_permission_id_84c5c92e_fk_auth_perm;

        ALTER TABLE auth_group_permissions
            DROP CONSTRAINT IF EXISTS auth_group_permiss_permission_id_84c5c92e_fk_auth_permission_id;

        ALTER TABLE accounts_permissionsetpermission
            DROP CONSTRAINT IF EXISTS accounts_permissions_permission_id_5b7e3342_fk_auth_perm;


        FOR row IN SELECT * FROM public.auth_permission
            LOOP
                UPDATE public.auth_permission SET id = row.id + BASE_ID WHERE id = row.id;

                UPDATE auth_group_permissions SET permission_id = row.id + BASE_ID WHERE permission_id = row.id;

                UPDATE accounts_permissionsetpermission
                SET permission_id = row.id + BASE_ID
                WHERE permission_id = row.id;

            END LOOP;

        FOR row IN SELECT *
                   FROM auth_permission
                   WHERE NOT codename LIKE '%:%'
                   UNION ALL
                   SELECT *
                   FROM auth_permission
                   WHERE codename LIKE '%:%'
            LOOP
                IF row.id > BASE_ID THEN
                    SELECT id
                    INTO NEW_ID
                    FROM auth_permission_temp
                    WHERE codename = row.codename
                      AND content_type_id = row.content_type_id;


                    IF NEW_ID IS NOT NULL THEN
                        UPDATE public.auth_permission SET id = NEW_ID WHERE id = row.id;
                    ELSE
                        SELECT NEXTVAL('auth_permission_id_seq') INTO NEW_ID;
                        UPDATE public.auth_permission SET id = NEW_ID WHERE id = row.id;
                    END IF;

                    -- update references
                    UPDATE auth_group_permissions SET permission_id = NEW_ID WHERE permission_id = row.id;

                    UPDATE accounts_permissionsetpermission
                    SET permission_id = NEW_ID
                    WHERE permission_id = row.id;
                END IF;
            END LOOP;

    END;
$$
"""


JSON_FILE = f"{settings.BASE_DIR}/core/migrations/data/golden_set_permissions.json"


def insert_into_temp_permissions(apps, schema_editor):
    # Get the model for AuthPermissionTemporal
    AuthPermissionTemporal = apps.get_model(app_label="core", model_name="AuthPermissionTemporal")

    # Create an empty list to store the temporary data
    temporal_data = []

    # Open the JSON file and retrieve the base permissions
    base_permissions = load_from_file(file_path=JSON_FILE)

    # Iterate over each permission in the base permissions
    for permission in base_permissions:
        # Create an instance of AuthPermissionTemporal with the permission data
        temporal_data.append(AuthPermissionTemporal(id=permission["pk"], **permission["fields"]))

    # Bulk create the AuthPermissionTemporal instances
    AuthPermissionTemporal.objects.bulk_create(temporal_data)


def remove_duplicate_permissions_from_golden_set(apps, schema_editor):
    AuthPermission = apps.get_model(app_label="auth", model_name="Permission")
    AuthPermissionTemporal = apps.get_model(app_label="core", model_name="AuthPermissionTemporal")

    duplicates = AuthPermission.objects.values("codename").annotate(Count("id")).order_by().filter(id__count__gt=1)

    for duplicate in duplicates:
        codename_in_golden_set = AuthPermissionTemporal.objects.filter(codename=duplicate["codename"])
        if codename_in_golden_set.exists():
            permission_ids_to_exclude = codename_in_golden_set.values_list("id", flat=True)
            # Get permissions to delete, excluding those in AuthPermissionTemporal
            permissions_to_delete = AuthPermission.objects.filter(codename=duplicate["codename"]).exclude(
                id__in=permission_ids_to_exclude
            )
            # Delete the permissions
            permissions_to_delete.delete()
        else:
            PermissionSet = apps.get_model(app_label="accounts", model_name="PermissionSet")
            excluded_ids = []

            for permission_set in PermissionSet.objects.all():
                excluded_ids.append(permission_set.permissions.all().values_list("id", flat=True))

            # If the codename is not in Goldenset, delete first permissions with that codename
            AuthPermission.objects.filter(codename=duplicate["codename"]).exclude(id__in=excluded_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_create_all_permissions"),
    ]

    operations = [
        migrations.RunPython(
            set_permissions_set_hash,
            migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name="AuthPermissionTemporal",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                (
                    "content_type",
                    models.ForeignKey(to="contenttypes.ContentType", on_delete=django.db.models.deletion.CASCADE),
                ),
                ("codename", models.CharField(max_length=100)),
            ],
            options={
                "db_table": "auth_permission_temp",
                "unique_together": {("content_type", "codename")},
            },
        ),
        migrations.RunPython(
            insert_into_temp_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunSQL(
            sql=SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(remove_duplicate_permissions_from_golden_set, reverse_code=migrations.RunPython.noop),
        migrations.DeleteModel(
            name="AuthPermissionTemporal",
        ),
        migrations.RunPython(
            create_csv,
            migrations.RunPython.noop,
        ),
    ]
