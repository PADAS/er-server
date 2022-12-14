# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-06-23 06:05
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0038_observations_commonname'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commonname',
            name='subject_subtype',
            field=models.CharField(choices=[('Wildlife', (('elephant', 'Elephant'), ('zebra', 'Zebra'), ('rhino', 'Rhino'), ('lion', 'Lion'), ('giraffe', 'Giraffe'), ('antelope', 'Antelope'), ('cheetah', 'Cheetah'), ('cow', 'Cow'), ('forest_elephant', 'Forest Elephant'), ('sable', 'Sable'), ('scimitar_oryx', 'Scimitar Oryx'), ('undeployed', 'Undeployed'))), ('Person', (('ranger', 'Ranger'), ('ranger_team', 'Ranger Team'), ('driver', 'Driver'), ('manager', 'Manager'), (
                'expedition', 'Expedition'))), ('Vehicle', (('security_vehicle', 'Security Vehicle'), ('research', 'Research Vehicle'), ('tourist_vehicle', 'Tourist Vehicle'), ('motorcycle', 'Motorcycle'))), ('Stationary Sensor', (('camera-trap', 'Camera Trap'), ('weather-station', 'Weather Sensor'))), ('Aircraft', (('plane', 'Plane'), ('helicopter', 'Helicopter'), ('drone', 'Drone'))), ('Unassigned', (('unassigned', 'Unassigned'),))], max_length=100),
        ),
        migrations.AlterField(
            model_name='subject',
            name='subject_subtype',
            field=models.CharField(choices=[('Wildlife', (('elephant', 'Elephant'), ('zebra', 'Zebra'), ('rhino', 'Rhino'), ('lion', 'Lion'), ('giraffe', 'Giraffe'), ('antelope', 'Antelope'), ('cheetah', 'Cheetah'), ('cow', 'Cow'), ('forest_elephant', 'Forest Elephant'), ('sable', 'Sable'), ('scimitar_oryx', 'Scimitar Oryx'), ('undeployed', 'Undeployed'))), ('Person', (('ranger', 'Ranger'), ('ranger_team', 'Ranger Team'), ('driver', 'Driver'), ('manager', 'Manager'), ('expedition', 'Expedition'))), (
                'Vehicle', (('security_vehicle', 'Security Vehicle'), ('research', 'Research Vehicle'), ('tourist_vehicle', 'Tourist Vehicle'), ('motorcycle', 'Motorcycle'))), ('Stationary Sensor', (('camera-trap', 'Camera Trap'), ('weather-station', 'Weather Sensor'))), ('Aircraft', (('plane', 'Plane'), ('helicopter', 'Helicopter'), ('drone', 'Drone'))), ('Unassigned', (('unassigned', 'Unassigned'),))], db_column='subject_subtype', default='unassigned', max_length=100),
        ),
    ]
