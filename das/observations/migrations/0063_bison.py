# Generated by Django 2.0.2 on 2019-01-07 20:12

from django.db import migrations, models
import django.db.models.deletion
import observations.models


NEW_ANIMALS = [{'display': 'Bison', 'value': 'bison'},
               {'display': 'Swift Fox', 'value': 'swift_fox'},
               {'display': 'Gray Wolf', 'value': 'gray_wolf'},
                ]

SUBJECT_TYPE_VALUE = 'wildlife'

def load_bison_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects.using(db_alias).get(value=SUBJECT_TYPE_VALUE)
    for subtype in NEW_ANIMALS:
        defaults = {'display': subtype['display'],
                    'subject_type': subject_type}
        SubjectSubType.objects.using(db_alias).get_or_create(value=subtype['value'],
                                                         defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0062_awt'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subject',
            name='subject_subtype',
            field=models.ForeignKey(default=observations.models.get_default_subject_subtype, on_delete=django.db.models.deletion.PROTECT, to='observations.SubjectSubType'),
        ),
        migrations.RunPython(load_bison_subtypes,
                             reverse_code=migrations.RunPython.noop),
    ]