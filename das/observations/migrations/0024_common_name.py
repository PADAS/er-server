# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2016-10-07 19:14
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0023_feature_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommonName',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subject_subtype', models.CharField(choices=[('Wildlife', (('elephant', 'Elephant'), ('zebra', 'Zebra'), ('rhino', 'Rhino'), ('lion', 'Lion'))), ('Person', (('ranger', 'Ranger'), ('ranger_team', 'Ranger Team'), ('driver', 'Driver'), ('manager', 'Manager'))), ('Vehicle', (('security', 'Security Vehicle'), ('research', 'Research Vehicle'), ('motorcycle', 'Motorcycle'))), ('Stationary Sensor', (('camera-trap', 'Camera Trap'), ('weather-station', 'Weather Sensor'))), ('Aircraft', (('plane', 'Plane'), ('helicopter', 'Helicopter')))], max_length=100)),
                ('value', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('display', models.CharField(max_length=100)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='subject',
            name='common_name',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='observations.CommonName'),
        ),
    ]
