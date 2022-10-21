# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-09-15 16:28
from __future__ import unicode_literals

import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0041_camera'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocketClient',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(db_column='sid',
                                        default=uuid.uuid4, primary_key=True, serialize=False)),
                ('username', models.CharField(max_length=30,
                                              verbose_name='Das username associated with session')),
                ('bbox', django.contrib.gis.db.models.fields.MultiPolygonField(
                    blank=True, null=True, srid=4326, verbose_name='Viewport bounding box.')),
                ('event_filter', django.contrib.postgres.fields.jsonb.JSONField(
                    default={}, verbose_name='Event filter')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]