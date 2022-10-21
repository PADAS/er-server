# Generated by Django 2.0.2 on 2019-01-14 18:54

from django.db import migrations, models
import django.db.models.deletion
import observations.models


NEW_ANIMALS = [{'display': 'Wildebeest', 'value': 'wildebeest'},
               ]

SUBJECT_TYPE_VALUE = 'wildlife'


def load_wildebeest_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects.using(
        db_alias).get(value=SUBJECT_TYPE_VALUE)
    for subtype in NEW_ANIMALS:
        defaults = {'display': subtype['display'],
                    'subject_type': subject_type}
        SubjectSubType.objects.using(db_alias).get_or_create(value=subtype['value'],
                                                             defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0063_bison'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubjectStatusLatest',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
            },
            bases=('observations.subjectstatus',),
        ),
        migrations.AlterField(
            model_name='subject',
            name='subject_subtype',
            field=models.ForeignKey(default=observations.models.get_default_subject_subtype,
                                    on_delete=django.db.models.deletion.PROTECT, to='observations.SubjectSubType'),
        ),
        migrations.RunPython(load_wildebeest_subtypes,
                             reverse_code=migrations.RunPython.noop),
    ]