# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2016-12-03 00:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0046_serial_number_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='related_events',
            field=models.ManyToManyField(related_name='_event_related_events_+', through='activity.EventRelationship', to='activity.Event'),
        ),
        migrations.AlterField(
            model_name='event',
            name='end_time',
            field=models.DateTimeField(blank=True, null=True, verbose_name='End Time'),
        ),
    ]
