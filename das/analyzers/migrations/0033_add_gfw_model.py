# Generated by Django 2.0.13 on 2019-07-23 21:50

import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0018_tile'),
        ('analyzers', '0032_rename_gee_analyzer'),
    ]

    operations = [
        migrations.CreateModel(
            name='GlobalForestWatchSubscription',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('subscription_id', models.CharField(blank=True, max_length=100)),
                ('geostore_id', models.CharField(blank=True, max_length=100)),
                ('additional', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict, help_text='JSON data for subscriptions')),
                ('subscription_geometry', django.contrib.gis.db.models.fields.PolygonField(geography=True, null=True, srid=4326)),
            ],
            options={
                'abstract': False,
                'verbose_name': 'Global Forest Watch Subscription',
                'verbose_name_plural': 'Global Forest Watch Subscriptions',
            },
        ),
    ]
