# Generated by Django 2.0.3 on 2020-02-07 14:09

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import observations.models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0073_husky'),
    ]

    operations = [
        migrations.AlterField(
            model_name='observation',
            name='additional',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        )
    ]
