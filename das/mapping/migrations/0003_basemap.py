# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0002_auto_20150921_1620'),
    ]

    operations = [
        migrations.CreateModel(
            name='BaseMap',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, serialize=False)),
                ('name', models.CharField(unique=True, max_length=80)),
                ('description', models.TextField(null=True, blank=True)),
                ('raster_file', models.CharField(unique=True, max_length=80)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
