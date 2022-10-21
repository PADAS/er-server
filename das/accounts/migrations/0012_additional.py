# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2017-03-05 16:40
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_auto_20161129_1227'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='additional',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default={}, null=True, verbose_name='additional data'),
        ),
    ]