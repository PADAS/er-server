# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-21 19:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0035_null_eventtype'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventtype',
            name='schema',
            field=models.TextField(blank=True),
        ),
    ]
