# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import uuid
import django.contrib.postgres.fields
import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.ranges


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Observation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, serialize=False, primary_key=True)),
                ('location', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('recorded_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('additional', django.contrib.postgres.fields.JSONField()),
            ],
        ),
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, serialize=False, primary_key=True)),
                ('source_type', models.CharField(max_length=100, choices=[('tracking-device', 'Tracking Device'), ('trap', 'Trap'), ('seismic', 'Seismic sensor'), ('firms', 'FIRMS data'), ('gps-radio', 'gps radio')], null=True, verbose_name='type of data expected')),
                ('manufacturer_id', models.CharField(max_length=100, null=True, verbose_name='device manufacturer id')),
                ('model_name', models.CharField(max_length=100, null=True, verbose_name='device model name')),
                ('additional', django.contrib.postgres.fields.JSONField()),
            ],
        ),
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('additional', django.contrib.postgres.fields.JSONField()),
            ],
        ),
        migrations.CreateModel(
            name='SubjectSource',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, serialize=False, primary_key=True)),
                ('assigned_range', django.contrib.postgres.fields.ranges.DateTimeRangeField()),
                ('additional', django.contrib.postgres.fields.JSONField()),
                ('source', models.ForeignKey(to='observations.Source', on_delete=models.CASCADE)),
                ('subject', models.ForeignKey(to='observations.Subject', on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='observation',
            name='source',
            field=models.ForeignKey(to='observations.Source', on_delete=models.CASCADE),
        ),
        migrations.AlterIndexTogether(
            name='observation',
            index_together=set([('source', 'recorded_at')]),
        ),
    ]
