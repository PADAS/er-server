# -*- coding: utf-8 -*-
# Generated by Django 1.9.6 on 2016-05-11 16:59
from __future__ import unicode_literals

import uuid

import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import revision.manager


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activity', '0010_use_al'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventRevision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('object_id', models.UUIDField()),
                ('action', models.IntegerField(choices=[(1, 'Added'), (2, 'Changed'), (3, 'Deleted')], default=1)),
                ('changed', models.CharField(choices=[('field', 'Field(s) Changed')], default='', max_length=20)),
                ('revision_at', models.DateTimeField(auto_now_add=True)),
                ('sequence', models.IntegerField(help_text='Revision sequence')),
                ('data', django.contrib.postgres.fields.jsonb.JSONField(default={})),
                ('user', revision.manager.UserField(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='_event_revision', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'default_permissions': (),
            },
        ),
        migrations.AlterUniqueTogether(
            name='eventrevision',
            unique_together=set([('object_id', 'sequence')]),
        ),
    ]