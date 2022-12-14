# Generated by Django 2.0.2 on 2018-06-22 21:22

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0023_post-django2-upgrade'),
    ]

    operations = [
        migrations.AlterField(
            model_name='speeddistro',
            name='percentiles',
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='subjectanalyzerresult',
            name='values',
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True, default=dict),
        ),
    ]
