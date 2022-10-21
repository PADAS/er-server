# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2016-12-20 05:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0009_use_al'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='immobilityanalyzer',
            name='threshold_critical_cluster_ratio',
        ),
        migrations.RemoveField(
            model_name='immobilityanalyzer',
            name='threshold_warning_cluster_ratio',
        ),
        migrations.AddField(
            model_name='immobilityanalyzer',
            name='search_time_hours',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='immobilityanalyzer',
            name='threshold_probability',
            field=models.FloatField(default=0.8),
        ),
    ]
