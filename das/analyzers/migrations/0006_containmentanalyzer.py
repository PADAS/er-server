# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-02-01 23:28
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0002_map'),
        ('analyzers', '0005_auto_20160201_1504'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContainmentAnalyzer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_time', models.TimeField(null=True)),
                ('max_time', models.TimeField(null=True)),
                ('interior_buffer', models.FloatField(default=0.0)),
                ('polygon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mapping.PolygonFeature')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
