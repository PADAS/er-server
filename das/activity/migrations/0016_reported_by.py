# -*- coding: utf-8 -*-
# Generated by Django 1.9.6 on 2016-05-19 12:17
from __future__ import unicode_literals

import activity.models
from django.conf import settings
import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('activity', '0015_attachment_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='reported_by_content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='event',
            name='reported_by_id',
            field=models.UUIDField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='attributes',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default={}),
        ),
        migrations.AlterField(
            model_name='event',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET(activity.models.get_sentinel_user), related_name='events', related_query_name='event', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='event',
            name='location',
            field=django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326),
        ),
    ]
