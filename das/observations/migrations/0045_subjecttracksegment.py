# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-11-06 23:03
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0044_schedule'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='subjecttracksegmentfilter',
            name='subject_type',
        ),
        migrations.AddField(
            model_name='subjecttracksegmentfilter',
            name='subject_subtype',
            field=models.TextField(default='elephant'),
        ),
    ]