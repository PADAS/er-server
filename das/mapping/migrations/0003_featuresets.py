# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2016-08-03 23:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0002_map'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='featureset',
            name='type',
        ),
        migrations.AddField(
            model_name='featureset',
            name='types',
            field=models.ManyToManyField(related_name='featuresets', to='mapping.FeatureType'),
        ),
    ]
