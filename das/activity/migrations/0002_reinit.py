# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-01-14 17:28
from __future__ import unicode_literals

import activity.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activity', '0001_init'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventAttachment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_id', models.UUIDField()),
                ('reason', models.CharField(choices=[('target', 'Target')], default='target', max_length=20)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
            ],
        ),
        migrations.RemoveField(
            model_name='event',
            name='user',
        ),
        migrations.AddField(
            model_name='event',
            name='created_by_user',
            field=models.ForeignKey(null=True, on_delete=models.SET(activity.models.get_sentinel_user), related_name='events', related_query_name='event', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='event',
            name='event_type',
            field=models.CharField(choices=[('default', 'System Event'), ('alert', 'Analyzer')], default='default', max_length=20),
        ),
        migrations.AlterField(
            model_name='event',
            name='name',
            field=models.CharField(max_length=80),
        ),
        migrations.AlterField(
            model_name='event',
            name='provenance',
            field=models.CharField(choices=[('system', 'System Process'), ('sensor', 'Sensor'), ('analyzer', 'Analyzer'), ('informant', 'Informant')], default='system', max_length=20),
        ),
        migrations.AddField(
            model_name='eventattachment',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', related_query_name='attachment', to='activity.Event'),
        ),
    ]
