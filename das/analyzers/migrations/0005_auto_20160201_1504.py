# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-02-01 23:04
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0002_map'),
        ('analyzers', '0004_auto_20160129_1406'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='geofenceanalyzer',
            name='interior_buffer',
        ),
        migrations.RemoveField(
            model_name='geofenceanalyzer',
            name='polygon',
        ),
        migrations.AddField(
            model_name='geofenceanalyzer',
            name='fence',
            field=models.ForeignKey(default='', on_delete=django.db.models.deletion.CASCADE, to='mapping.LineFeature'),
            preserve_default=False,
        ),
    ]