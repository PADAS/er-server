# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-03-30 21:20
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0008_auto_20160217_1427'),
    ]

    operations = [
        migrations.AlterField(
            model_name='speedanalyzer',
            name='max_speed',
            field=models.FloatField(default=8),
        ),
    ]
