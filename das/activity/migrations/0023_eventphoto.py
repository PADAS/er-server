# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-06-27 17:21
from __future__ import unicode_literals

import activity.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid
import versatileimagefield.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activity', '0021_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventPhoto',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('image', versatileimagefield.fields.VersatileImageField(max_length=512, null=True, upload_to=activity.models.upload_to)),
                ('created_by_user', models.ForeignKey(blank=True, null=True, on_delete=models.SET(activity.models.get_sentinel_user), related_name='event_photos', related_query_name='event_photo', to=settings.AUTH_USER_MODEL)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', related_query_name='photo', to='activity.Event')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
