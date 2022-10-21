# Generated by Django 2.2.9 on 2021-01-05 09:47

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0087_er_track_source_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='socketclient',
            name='patrol_filter',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict, verbose_name='Patrol filter'),
        ),
    ]
