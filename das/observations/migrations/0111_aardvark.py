# Generated by Django 2.2.14 on 2021-10-18 15:25

from django.db import migrations, models
import django.db.models.deletion
import observations.models


NEW_SUBTYPES = [
    {'display': 'Aardvark', 'value': 'aardvark'},
    {'display': 'Brown Hyena', 'value': 'brownhyena'},
    {'display': 'Spotted Hyena', 'value': 'spottedhyena'},
    
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
        ('observations', '0110_sensors'),
    ]

    operations = [
        migrations.RunPython(load_new_subtypes,
                             reverse_code=migrations.RunPython.noop),
    ]
