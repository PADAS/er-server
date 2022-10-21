# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-04-01 18:58
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0008_featuretype'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tilelayer',
            name='tile_type',
            field=models.CharField(choices=[('mbtiles', 'Local MBTiles'), ('external', 'External Tile Server')], default='mbtiles', max_length=20),
        ),
    ]