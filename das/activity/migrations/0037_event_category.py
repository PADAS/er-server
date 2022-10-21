# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-29 21:52
from __future__ import unicode_literals

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0036_et_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventCategory',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('value', models.CharField(max_length=40, unique=True)),
                ('display', models.CharField(blank=True, max_length=100)),
                ('ordernum', models.SmallIntegerField(blank=True, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='eventtype',
            name='category',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='activity.EventCategory'),
        ),

    ]
