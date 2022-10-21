# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2017-03-27 22:45
from __future__ import unicode_literals

import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0010_annotations'),
        ('observations', '0033_annotations'),
        ('analyzers', '0011_immobility_analyzer_result'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeofenceAnalyzerResult',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('crosstime', models.DateTimeField()),
                ('crosspoint', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('total_fix_count', models.IntegerField()),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField()),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ObservationAnnotator',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('max_speed', models.FloatField(default=10.0, verbose_name='Maximum speed (km/h)')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='observations.Subject')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RemoveField(
            model_name='geofenceanalyzer',
            name='fence',
        ),
        migrations.AddField(
            model_name='geofenceanalyzer',
            name='containment_regions',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='containmentregions', to='mapping.FeatureSet'),
        ),
        migrations.AddField(
            model_name='geofenceanalyzer',
            name='search_time_hours',
            field=models.FloatField(default=24.0),
        ),
        migrations.AddField(
            model_name='geofenceanalyzer',
            name='virtual_fences',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='virtualfences', to='mapping.FeatureSet'),
        ),
        migrations.AlterField(
            model_name='immobilityanalyzer',
            name='search_time_hours',
            field=models.FloatField(default=24.0),
        ),
        migrations.AddField(
            model_name='geofenceanalyzerresult',
            name='analyzer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='analyzers.GeofenceAnalyzer'),
        ),
        migrations.AddField(
            model_name='geofenceanalyzerresult',
            name='observations',
            field=models.ManyToManyField(related_name='_geofenceanalyzerresult_observations_+', to='observations.Observation'),
        ),
    ]
