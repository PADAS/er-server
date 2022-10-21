# -*- coding: utf-8 -*-
# Generated by Django 1.9a1 on 2015-10-06 14:21
from __future__ import unicode_literals

import django.contrib.gis.db.models.fields
from django.db import migrations, models
import django.db.models.deletion
import django.contrib.postgres.fields
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureSet',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='FeatureType',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='LineFeature',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('presentation', django.contrib.postgres.fields.JSONField()),
                ('feature_geometry', django.contrib.gis.db.models.fields.MultiLineStringField(srid=4326)),
                ('featureset', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureSet')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PointFeature',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('presentation', django.contrib.postgres.fields.JSONField()),
                ('feature_geometry', django.contrib.gis.db.models.fields.MultiPointField(srid=4326)),
                ('featureset', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureSet')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PolygonFeature',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('presentation', django.contrib.postgres.fields.JSONField()),
                ('feature_geometry', django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326)),
                ('featureset', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureSet')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='featureset',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mapping.FeatureType'),
        ),
    ]
