# -*- coding: utf-8 -*-
# Generated by Django 1.9.6 on 2016-05-17 16:50
from __future__ import unicode_literals

import activity.models
from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import revision.manager
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activity', '0012_event_message'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventAttachmentRevision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('object_id', models.UUIDField()),
                ('action', models.CharField(choices=[('added', 'Added'), ('updated', 'Updated'), ('deleted', 'Deleted')], default='added', max_length=10)),
                ('revision_at', models.DateTimeField(auto_now_add=True)),
                ('sequence', models.IntegerField(help_text='Revision sequence')),
                ('data', django.contrib.postgres.fields.jsonb.JSONField(default={})),
                ('user', revision.manager.UserField(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='_eventattachment_revision', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'default_permissions': (),
            },
        ),
        migrations.CreateModel(
            name='EventNote',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('created_by_user', models.ForeignKey(null=True, on_delete=models.SET(activity.models.get_sentinel_user), to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
            bases=(revision.manager.RevisionMixin, models.Model),
        ),
        migrations.CreateModel(
            name='EventNoteRevision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('object_id', models.UUIDField()),
                ('action', models.CharField(choices=[('added', 'Added'), ('updated', 'Updated'), ('deleted', 'Deleted')], default='added', max_length=10)),
                ('revision_at', models.DateTimeField(auto_now_add=True)),
                ('sequence', models.IntegerField(help_text='Revision sequence')),
                ('data', django.contrib.postgres.fields.jsonb.JSONField(default={})),
                ('user', revision.manager.UserField(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='_eventnote_revision', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'default_permissions': (),
            },
        ),
        migrations.AlterField(
            model_name='event',
            name='message',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='provenance',
            field=models.CharField(choices=[('staff', 'Staff'), ('system', 'System Process'), ('sensor', 'Sensor'), ('analyzer', 'Analyzer'), ('community', 'Community')], default='system', max_length=40),
        ),
        migrations.AddField(
            model_name='eventnote',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notes', related_query_name='note', to='activity.Event'),
        ),
        migrations.AlterUniqueTogether(
            name='eventnoterevision',
            unique_together=set([('object_id', 'sequence')]),
        ),
        migrations.AlterUniqueTogether(
            name='eventattachmentrevision',
            unique_together=set([('object_id', 'sequence')]),
        ),
    ]
