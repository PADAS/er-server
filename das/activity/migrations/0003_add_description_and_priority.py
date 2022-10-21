# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-04 17:40
from __future__ import unicode_literals

import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0002_reinit'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='description',
            field=models.TextField(default=''),
        ),
        migrations.AddField(
            model_name='event',
            name='priority',
            field=models.PositiveSmallIntegerField(choices=[(300, 'Urgent'), (200, 'Important'), (100, 'Reference')], default=100),
        ),
        migrations.AlterField(
            model_name='event',
            name='event_type',
            field=models.CharField(choices=[('system', 'System'), ('fence-breach', 'Fence Breach'), ('elephant-sighting', 'Elephant Sighting'), ('wounded-animal', 'Wounded Animal'), ('livestock-theft', 'Livestock Theft'), ('fire', 'Fire'), ('proximity', 'Proximity'), ('geofence', 'Geofence'), ('immobility', 'Immobility'), ('speed', 'Speed')], default='system', max_length=20),
        ),
        migrations.AlterField(
            model_name='event',
            name='location',
            field=django.contrib.gis.db.models.fields.PointField(null=True, srid=4326),
        ),
    ]