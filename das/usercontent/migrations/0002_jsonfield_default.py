# Generated by Django 2.0.2 on 2018-06-22 21:22

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('usercontent', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='filecontentrevision',
            name='data',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='imagefilecontentrevision',
            name='data',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]