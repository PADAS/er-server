# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-30 16:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_ordernum'),
    ]

    operations = [
        migrations.CreateModel(
            name='DynamicChoice',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('model_name', models.CharField(max_length=100, verbose_name='Model lookup')),
                ('criteria', models.CharField(max_length=100, verbose_name='Criteria')),
                ('value_col', models.CharField(max_length=100, verbose_name='Value column')),
                ('display_col', models.CharField(max_length=100, verbose_name='Display column')),
            ],
        ),
    ]
