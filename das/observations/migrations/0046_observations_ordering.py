# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2018-01-06 01:13
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0045_subjecttracksegment'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='observation',
            options={'ordering': ['-recorded_at']},
        ),
    ]
