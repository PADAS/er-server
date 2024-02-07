import json

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

SQL = """
DO
$$
    DECLARE
        ROW     RECORD;
        NEW_ID  INTEGER;
        BASE_ID INTEGER;
    BEGIN
        BASE_ID = 10000;
        -- DROP FK
        ALTER TABLE auth_group_permissions
            DROP CONSTRAINT auth_group_permissio_permission_id_84c5c92e_fk_auth_perm;

        ALTER TABLE accounts_permissionsetpermission
            DROP CONSTRAINT accounts_permissions_permission_id_5b7e3342_fk_auth_perm;


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


def open_json_file(json_file: str):
    with open(json_file, "r") as json_file:
        return json.load(json_file)


def insert_into_temp_permissions(apps, schema_editor):
    AuthPermissionTemporal = apps.get_model(app_label="core", model_name="AuthPermissionTemporal")
    temporal_data = []
    json_file = f"{settings.BASE_DIR}/core/migrations/data/golden_set_permissions.json"

    base_permissions = open_json_file(json_file=json_file)

    for permission in base_permissions:
        temporal_data.append(AuthPermissionTemporal(id=permission["pk"], **permission["fields"]))

    AuthPermissionTemporal.objects.bulk_create(temporal_data)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_set_base_content_types"),
    ]

    operations = [
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
        migrations.DeleteModel(
            name="AuthPermissionTemporal",
        ),
    ]
