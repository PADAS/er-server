# Generated by Django 2.2.11 on 2020-05-16 13:50

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import observations.models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0036_meta'),
        ('observations', '0076_ibex'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubjectMaximumSpeed',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('analyzers.observationannotator',),
        ),
        migrations.CreateModel(
            name='SubjectSourceSummary',
            fields=[
            ],
            options={
                'verbose_name': 'Subject Configuration',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('observations.subjectsource',),
        ),
        migrations.AlterModelOptions(
            name='source',
            options={},
        ),
        migrations.AlterModelOptions(
            name='sourcegroup',
            options={'verbose_name': 'source group', 'verbose_name_plural': 'source groups'},
        ),
        migrations.AlterModelOptions(
            name='subjectgroup',
            options={'verbose_name': 'subject group', 'verbose_name_plural': 'subject groups'},
        ),
        migrations.AlterField(
            model_name='socketclient',
            name='event_filter',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict, verbose_name='Event filter'),
        ),
        migrations.AlterField(
            model_name='source',
            name='source_type',
            field=models.CharField(choices=[('firms', 'FIRMS data'), ('gps-radio', 'GPS radio'), ('seismic', 'Seismic sensor'), ('tracking-device', 'Tracking Device'), ('trap', 'Trap')], max_length=100, null=True, verbose_name='type of data expected'),
        ),
        migrations.AlterField(
            model_name='subject',
            name='subject_subtype',
            field=models.ForeignKey(default=observations.models.get_default_subject_subtype, on_delete=django.db.models.deletion.PROTECT, to='observations.SubjectSubType'),
        ),
    ]
