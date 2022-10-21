# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2017-03-14 19:28
from __future__ import unicode_literals

import datetime
import django.contrib.postgres.fields.jsonb
import django.contrib.postgres.fields.ranges
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0034_create_new_permissions'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='subject',
            options={'permissions': (('view_last_position', 'Permission to view the last reported position of a Subject only.'), ('view_real_time', 'Access to real-time observations.'), ('view_delayed', 'Access to a 24 hour delayed observation feed. No real-time or last reported position.'), ('subscribe_alerts', 'Permission to subscribe to an alert on this Subject.'), ('change_alerts', 'Permission to configure alerts for subject, includes setting geofences, proximity and immobility settings.'), ('change_view', 'An admin permission to change which users can view a Subject and their view permission.'), ('access_begins_7', 'Can view tracks no more than 7 days old'), ('access_begins_16', 'Can view tracks no more than 16 days old'), ('access_begins_30', 'Can view tracks no more than 30 days old'), ('access_begins_60', 'Can view tracks no more than 60 days old'), ('access_begins_all', 'Can view all historical tracks'), ('access_ends_0', 'Can view tracks no less than 0 days old'), ('access_ends_3', 'Can view tracks no less than 3 days old'), ('access_ends_7', 'Can view tracks no less than 7 days old'))},
        ),
    ]
