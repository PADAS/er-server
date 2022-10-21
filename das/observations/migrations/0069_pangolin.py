# Generated by Django 2.0.2 on 2019-02-28 17:44

from django.db import migrations, models
import django.db.models.deletion
import observations.models


NEW_SUBTYPES = [{'display': 'Pangolin', 'value': 'pangolin'},
                {'display': 'Orangutan', 'value': 'orangutan'},
                {'display': 'Wild Dog', 'value': 'wild_dog'},
                ]

SUBJECT_TYPE_VALUE = 'wildlife'


def load_new_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects.using(
        db_alias).get(value=SUBJECT_TYPE_VALUE)
    for subtype in NEW_SUBTYPES:
        defaults = {'display': subtype['display'],
                    'subject_type': subject_type}
        SubjectSubType.objects.using(db_alias).get_or_create(value=subtype['value'],
                                                             defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0068_balloon'),
    ]

    operations = [

        migrations.RunPython(load_new_subtypes,
                             reverse_code=migrations.RunPython.noop),
    ]
