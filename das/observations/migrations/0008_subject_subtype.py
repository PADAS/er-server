# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-10 21:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0007_subject_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='subject_subtype',
            field=models.CharField(choices=[('Wildlife', (('elephant', 'Elephant'), ('zebra', 'Zebra'), ('rhino', 'Rhino'), ('lion', 'Lion'))), ('Person', (('ranger', 'Ranger'), ('driver', 'Driver'), ('manager', 'Manager'))), ('Vehicle', (('security', 'Security Vehicle'), ('research', 'Research Vehicle'))), ('Stationary Sensor', (('camera-trap', 'Camera Trap'), ('weather-station', 'Weather Sensor')))], default='elephant', max_length=100),
        ),
        migrations.AlterField(
            model_name='subject',
            name='subject_type',
            field=models.CharField(choices=[('wildlife', 'Wildlife'), ('person', 'Person'), ('vehicle', 'Vehicle'), ('stationary-object', 'Stationary Sensor')], default='wildlife', max_length=100, verbose_name='subject type'),
        ),
    ]
