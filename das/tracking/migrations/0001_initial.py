# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-02-01 23:46
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('observations', '0006_auto_20160105_1055'),
        ('mapping', '0002_map'),
    ]

    operations = [
        migrations.CreateModel(
            name='AWTHttpPlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('service_api_url', models.URLField(default='http://www.yrless.co.za/STE/yrserv/datanew.phtml', help_text='The URL for the AWT service.')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='DemoSourcePlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('range_polygon', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mapping.PolygonFeature')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='FirmsPlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('service_username', models.CharField(help_text='The username for accessing FIRMS ftp site.', max_length=50)),
                ('service_password', models.CharField(help_text='The password for accessing FIRMS ftp site.', max_length=50)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='InreachKMLPlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('service_share_path', models.CharField(help_text='share_path for InReach KML share.', max_length=50)),
                ('service_password', models.CharField(help_text='Password for InReach KML share.', max_length=50)),
                ('service_username', models.CharField(help_text='Username for InReach KML share.', max_length=50)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='InreachPlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('service_username', models.CharField(help_text='The username for querying the InReach API service.', max_length=50)),
                ('service_password', models.CharField(help_text='The password for querying the InReach API service.', max_length=50)),
                ('service_api_host', models.CharField(help_text='the ip-address or host-name for the InReach API service.', max_length=50)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SavannahPlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('service_username', models.CharField(help_text='The username for querying the Savannah Tracking service.', max_length=50)),
                ('service_password', models.CharField(help_text='The password for querying the Savannah Tracking service.', max_length=50)),
                ('service_api_host', models.CharField(help_text='the ip-address or host-name for the Savannah Tracking service.', max_length=50)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SkygisticsSatellitePlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')),
                ('status', models.CharField(choices=[('enabled', 'Enabled'), ('disabled', 'Disabled')], default='enabled', max_length=15)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('service_username', models.CharField(help_text='The username for Skygistics API.', max_length=50)),
                ('service_password', models.CharField(help_text='The password for Skygistics API.', max_length=50)),
                ('service_api_url', models.CharField(default='http://skyq1.skygistics.com', help_text='API endpoint for Skygistics service.', max_length=50)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SourcePlugin',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('plugin_id', models.UUIDField()),
                ('cursor_data', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('status', models.CharField(default='enabled', max_length=15)),
                ('last_run', models.DateTimeField(auto_now_add=True, verbose_name='Timestamp for when this plugin last executed.')),
                ('plugin_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='source_plugins', related_query_name='source_plugin', to='observations.Source')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
