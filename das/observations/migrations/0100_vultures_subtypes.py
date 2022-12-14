# Generated by Django 2.2.9 on 2021-04-08 21:55

from django.db import migrations

NEW_SUBTYPES = [{"display": "Cape Vulture", "value": "cape_vulture"},
                {"display": "Hooded Vulture", "value": "hooded_vulture"},
                {"display": "Lappet-faced Vulture", "value": "lappet_faced_vulture"},
                {"display": "Martial Eagle", "value": "martial_eagle"},
                {"display": "White-backed Vulture", "value": "white_backed_vulture"}]


def forwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    subject_type_model = apps.get_model('observations', 'SubjectType')
    subject_subtype_model = apps.get_model('observations', 'SubjectSubType')

    subject_type = subject_type_model.objects.using(db_alias).get(value='wildlife')

    for subtype in NEW_SUBTYPES:
        defaults = {'display': subtype['display'],  'subject_type': subject_type}
        subject_subtype_model.objects.using(db_alias).get_or_create(value=subtype['value'],
                                                                    defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0099_two_way'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)
    ]
