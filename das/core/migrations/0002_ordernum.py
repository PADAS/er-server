# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-06-27 18:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='choice',
            name='ordernum',
            field=models.SmallIntegerField(blank=True, null=True),
        ),
    ]
