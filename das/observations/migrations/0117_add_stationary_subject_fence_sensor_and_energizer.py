# Generated by Django 2.2.24 on 2022-04-05 20:29

from django.db import migrations

NEW_SUBTYPES = [
    {
        "display": "Fence Energizer",
        "value": "static_fence_energizer",
    },
    {
        "display": "Fence Sensor",
        "value": "static_fence_sensor",
    },
]
SUBJECT_TYPE_VALUE = 'stationary-object'


def load_new_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model("observations", "SubjectType")
    SubjectSubType = apps.get_model("observations", "SubjectSubType")
    subject_type = SubjectType.objects.using(db_alias).get(value=SUBJECT_TYPE_VALUE)

    for subtype in NEW_SUBTYPES:
        defaults = {
            "display": subtype["display"],
            "subject_type": subject_type,
        }
        SubjectSubType.objects.using(db_alias).get_or_create(
            value=subtype["value"], defaults=defaults
        )


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0116_shark_merge'),
    ]

    operations = [
        migrations.RunPython(load_new_subtypes, reverse_code=migrations.RunPython.noop),
    ]
