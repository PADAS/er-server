# Generated by Django 3.1 on 2022-07-29 14:56


from django.db import migrations

NEW_SUBTYPES = (
    {"display": "Shoebill", "value": "shoebill"},
)

SUBJECT_TYPE_VALUE = "wildlife"


def load_new_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model("observations", "SubjectType")
    SubjectSubType = apps.get_model("observations", "SubjectSubType")
    subject_type = SubjectType.objects.using(
        db_alias).get(value=SUBJECT_TYPE_VALUE)

    for subtype in NEW_SUBTYPES:
        defaults = {"display": subtype["display"],
                    "subject_type": subject_type}
        SubjectSubType.objects.using(db_alias).get_or_create(
            value=subtype["value"], defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0124_use_models_JSONField_instead_postgres_fields_JSONField'),
    ]

    operations = [
        migrations.RunPython(
            load_new_subtypes, reverse_code=migrations.RunPython.noop)
    ]
