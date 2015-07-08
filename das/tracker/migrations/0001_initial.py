# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_pgjson.fields
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CollectionHistory',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('outcome', models.CharField(max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.AutoField(serialize=False, primary_key=True)),
                ('extra', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='DeviceType',
            fields=[
                ('id', models.AutoField(serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('extra', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='Observation',
            fields=[
                ('id', models.AutoField(serialize=False, primary_key=True)),
                ('location', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('recorded_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('extra', django_pgjson.fields.JsonBField()),
                ('device', models.ForeignKey(to='tracker.Device')),
            ],
        ),
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('extra', django_pgjson.fields.JsonBField()),
            ],
        ),
        migrations.CreateModel(
            name='SubjectDevice',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('start_at', models.DateTimeField()),
                ('end_at', models.DateTimeField()),
                ('extra', django_pgjson.fields.JsonBField()),
                ('device', models.ForeignKey(to='tracker.Device')),
                ('thing', models.ForeignKey(to='tracker.Subject')),
            ],
        ),
        migrations.AddField(
            model_name='device',
            name='device_type',
            field=models.ForeignKey(to='tracker.DeviceType'),
        ),
        migrations.AddField(
            model_name='collectionhistory',
            name='device',
            field=models.ForeignKey(to='tracker.Device'),
        ),
    ]
