# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.contrib.gis.db.models.fields
import datetime
from django.utils.timezone import utc
import django_pgjson.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('manufacturer_id', models.CharField(max_length=100, null=True, verbose_name='device manufacturer id')),
                ('extra', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='DeviceType',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('extra', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='Observation',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('location', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('recorded_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('extra', django_pgjson.fields.JsonBField()),
                ('device', models.ForeignKey(to='sensors.Device')),
            ],
        ),
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('name', models.CharField(max_length=100)),
                ('extra', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='SubjectDevice',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('start_at', models.DateTimeField()),
                ('end_at', models.DateTimeField(default=datetime.datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=utc))),
                ('extra', django_pgjson.fields.JsonBField()),
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
