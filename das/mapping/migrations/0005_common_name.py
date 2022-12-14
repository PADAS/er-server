# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2016-10-07 19:14
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0004_feature_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='linefeature',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default={}),
        ),
        migrations.AlterField(
            model_name='pointfeature',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default={}),
        ),
        migrations.AlterField(
            model_name='polygonfeature',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default={}),
        ),
    ]
