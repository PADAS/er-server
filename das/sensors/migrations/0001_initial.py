# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.contrib.postgres.fields
import django_pgjson.fields
import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.ranges


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('manufacturer_id', models.CharField(verbose_name='device manufacturer id', max_length=100, null=True)),
                ('additional', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='DeviceType',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('categories', django.contrib.postgres.fields.ArrayField(size=None, base_field=models.CharField(blank=True, max_length=50))),
                ('additional', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='Observation',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('location', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('recorded_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('additional', django_pgjson.fields.JsonBField()),
                ('device', models.ForeignKey(to='sensors.Device')),
            ],
        ),
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('additional', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='SubjectDevice',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('assigned_range', django.contrib.postgres.fields.ranges.DateTimeRangeField()),
                ('additional', django_pgjson.fields.JsonBField()),
                ('device', models.ForeignKey(to='sensors.Device')),
                ('subject', models.ForeignKey(to='sensors.Subject')),
            ],
        ),
        migrations.AddField(
            model_name='device',
            name='device_type',
            field=models.ForeignKey(to='sensors.DeviceType'),
        ),
    ]
